"""Celery tasks for video transcoding."""

import logging
from datetime import datetime
from pathlib import Path

from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from bsvs.config import get_settings
from bsvs.db.models import Video, VideoVariant, TranscodeJob, VideoStatus, JobStatus
from bsvs.transcode.ffmpeg import probe_video, transcode_to_hls, extract_thumbnails
from bsvs.transcode.presets import get_applicable_presets

logger = logging.getLogger(__name__)


def get_sync_db_session():
    """Get a synchronous database session for Celery tasks."""
    settings = get_settings()
    db_url = settings.database_url

    # Convert async URL to sync URL
    if "+aiosqlite" in db_url:
        # SQLite: sqlite+aiosqlite:/// -> sqlite:///
        db_url = db_url.replace("+aiosqlite", "")
    elif "+asyncpg" in db_url:
        # PostgreSQL: postgresql+asyncpg:// -> postgresql://
        db_url = db_url.replace("+asyncpg", "")

    engine = create_engine(db_url)
    return Session(engine)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def transcode_video_task(self, video_id: str, input_path: str):
    """
    Celery task to transcode a video to multiple HLS quality levels.

    Args:
        video_id: The video's database ID
        input_path: Path to the original video file
    """
    settings = get_settings()
    logger.info(f"Starting transcode task for video {video_id}")

    session = get_sync_db_session()

    try:
        # Get video record
        video = session.execute(
            select(Video).where(Video.id == video_id)
        ).scalar_one_or_none()

        if not video:
            logger.error(f"Video {video_id} not found")
            return {"status": "error", "message": "Video not found"}

        # Create or get transcode job
        job = session.execute(
            select(TranscodeJob).where(TranscodeJob.video_id == video_id)
        ).scalar_one_or_none()

        if not job:
            job = TranscodeJob(
                video_id=video_id,
                status=JobStatus.PROCESSING.value,
                started_at=datetime.utcnow(),
            )
            session.add(job)

        job.status = JobStatus.PROCESSING.value
        job.started_at = datetime.utcnow()
        video.status = VideoStatus.PROCESSING.value
        session.commit()

        # Probe the video
        logger.info(f"Probing video: {input_path}")
        info = probe_video(input_path)
        video.duration_seconds = int(info.duration_seconds)
        session.commit()

        logger.info(f"Video info: {info.width}x{info.height}, {info.duration_seconds}s, {info.codec}")

        # Determine which presets to use based on source resolution
        presets = get_applicable_presets(
            source_height=info.height,
            requested=settings.presets_list,
        )
        logger.info(f"Using presets: {[p.name for p in presets]}")

        # Output directory
        output_dir = settings.storage_path / video_id / "transcoded"

        # Transcode each quality level
        total_presets = len(presets)
        for i, preset in enumerate(presets):
            # Update progress (0-80% for transcoding)
            progress = int((i / total_presets) * 80)
            job.progress = progress
            session.commit()

            # Update Celery task state
            self.update_state(
                state="TRANSCODING",
                meta={
                    "current": i + 1,
                    "total": total_presets,
                    "quality": preset.name,
                    "progress": progress,
                }
            )

            logger.info(f"Transcoding to {preset.name} ({i+1}/{total_presets})...")

            try:
                playlist_path = transcode_to_hls(
                    input_path=input_path,
                    output_dir=output_dir,
                    preset=preset,
                )

                # Calculate file size
                quality_dir = output_dir / preset.name
                total_size = sum(f.stat().st_size for f in quality_dir.iterdir())

                # Calculate width from height maintaining aspect ratio
                width = int(info.width * (preset.height / info.height))
                width = width - (width % 2)  # Ensure even

                # Create variant record
                variant = VideoVariant(
                    video_id=video_id,
                    quality=preset.name,
                    width=width,
                    height=preset.height,
                    bitrate=preset.bitrate_kbps,
                    file_path=str(playlist_path),
                    file_size_bytes=total_size,
                )
                session.add(variant)
                session.commit()

                logger.info(f"Completed {preset.name}: {total_size / 1024 / 1024:.1f} MB")

            except Exception as e:
                logger.error(f"Failed to transcode to {preset.name}: {e}")
                # Continue with other presets

        # Extract thumbnails (80-95%)
        job.progress = 85
        session.commit()

        self.update_state(
            state="THUMBNAILS",
            meta={"progress": 85, "step": "Generating thumbnails"}
        )

        logger.info("Extracting thumbnails...")
        thumb_dir = settings.storage_path / video_id / "thumbnails"
        try:
            thumbnails = extract_thumbnails(input_path, thumb_dir, count=4)
            logger.info(f"Generated {len(thumbnails)} thumbnails")
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")

        # Check if we have at least one variant
        variant_count = session.execute(
            select(VideoVariant).where(VideoVariant.video_id == video_id)
        ).scalars().all()

        if variant_count:
            job.status = JobStatus.COMPLETED.value
            job.progress = 100
            job.completed_at = datetime.utcnow()
            video.status = VideoStatus.READY.value
            logger.info(f"Transcode complete for video {video_id}")
        else:
            job.status = JobStatus.FAILED.value
            job.error_message = "No variants were created"
            video.status = VideoStatus.FAILED.value
            logger.error(f"Transcode failed: no variants created for {video_id}")

        session.commit()

        return {
            "status": "success" if variant_count else "failed",
            "video_id": video_id,
            "variants": len(variant_count),
        }

    except Exception as e:
        logger.exception(f"Transcode task failed for video {video_id}")

        # Update job status
        try:
            job = session.execute(
                select(TranscodeJob).where(TranscodeJob.video_id == video_id)
            ).scalar_one_or_none()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)[:500]
                job.completed_at = datetime.utcnow()

            video = session.execute(
                select(Video).where(Video.id == video_id)
            ).scalar_one_or_none()
            if video:
                video.status = VideoStatus.FAILED.value

            session.commit()
        except Exception:
            pass

        # Retry if applicable
        raise self.retry(exc=e)

    finally:
        session.close()
