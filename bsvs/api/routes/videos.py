"""Video upload and management endpoints."""

import logging
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsvs.config import get_settings
from bsvs.db import get_db, Video, VideoStatus, TranscodeJob, JobStatus
from bsvs.worker.tasks import transcode_video_task
from bsvs.api.ratelimit import limiter, RATE_LIMIT_UPLOAD

logger = logging.getLogger(__name__)
router = APIRouter()


class VideoResponse(BaseModel):
    """Video response model."""
    id: str
    title: str
    description: str | None
    original_filename: str
    duration_seconds: int | None
    status: str
    created_at: str
    embed_url: str

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    """List of videos response."""
    videos: list[VideoResponse]
    total: int


@router.post("", response_model=VideoResponse, status_code=201)
@limiter.limit(RATE_LIMIT_UPLOAD)
async def upload_video(
    request: Request,
    file: Annotated[UploadFile, File(description="Video file to upload")],
    title: Annotated[str, Form()] = "",
    description: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a new video file.

    The video will be saved and queued for transcoding to HLS format.
    Rate limited to 10 uploads per minute per IP.
    """
    settings = get_settings()

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check file size (rough estimate from content-length)
    max_size = settings.max_upload_size_mb * 1024 * 1024

    # Use filename as title if not provided
    if not title:
        title = Path(file.filename).stem

    # Create video record
    video = Video(
        title=title,
        description=description,
        original_filename=file.filename,
        status=VideoStatus.PENDING.value,
    )
    db.add(video)
    await db.flush()  # Get the ID

    # Create transcode job record
    job = TranscodeJob(
        video_id=video.id,
        status=JobStatus.QUEUED.value,
        progress=0,
    )
    db.add(job)

    # Create storage directory for this video
    video_dir = settings.storage_path / video.id / "original"
    video_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded file
    file_path = video_dir / file.filename
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved video {video.id} to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save video: {e}")
        raise HTTPException(status_code=500, detail="Failed to save video file")

    await db.commit()

    # Queue transcoding via Celery
    transcode_video_task.delay(video.id, str(file_path))
    logger.info(f"Queued transcode task for video {video.id}")

    return VideoResponse(
        id=video.id,
        title=video.title,
        description=video.description,
        original_filename=video.original_filename,
        duration_seconds=video.duration_seconds,
        status=video.status,
        created_at=video.created_at.isoformat(),
        embed_url=f"/embed/{video.id}",
    )


@router.get("", response_model=VideoListResponse)
async def list_videos(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """List all videos."""
    result = await db.execute(
        select(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit)
    )
    videos = result.scalars().all()

    count_result = await db.execute(select(Video))
    total = len(count_result.scalars().all())

    return VideoListResponse(
        videos=[
            VideoResponse(
                id=v.id,
                title=v.title,
                description=v.description,
                original_filename=v.original_filename,
                duration_seconds=v.duration_seconds,
                status=v.status,
                created_at=v.created_at.isoformat(),
                embed_url=f"/embed/{v.id}",
            )
            for v in videos
        ],
        total=total,
    )


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get video metadata by ID."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return VideoResponse(
        id=video.id,
        title=video.title,
        description=video.description,
        original_filename=video.original_filename,
        duration_seconds=video.duration_seconds,
        status=video.status,
        created_at=video.created_at.isoformat(),
        embed_url=f"/embed/{video.id}",
    )


@router.get("/{video_id}/status")
async def get_video_status(
    video_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get video transcoding status with job progress."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.variants))
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Get transcode job info
    job_result = await db.execute(
        select(TranscodeJob).where(TranscodeJob.video_id == video_id)
    )
    job = job_result.scalar_one_or_none()

    job_info = None
    if job:
        job_info = {
            "status": job.status,
            "progress": job.progress,
            "error_message": job.error_message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    return {
        "id": video.id,
        "status": video.status,
        "job": job_info,
        "variants": [
            {"quality": v.quality, "width": v.width, "height": v.height}
            for v in video.variants
        ],
    }


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a video and all its files."""
    settings = get_settings()

    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Delete files
    video_dir = settings.storage_path / video_id
    if video_dir.exists():
        shutil.rmtree(video_dir)
        logger.info(f"Deleted video directory: {video_dir}")

    # Delete database record
    await db.delete(video)
    await db.commit()
