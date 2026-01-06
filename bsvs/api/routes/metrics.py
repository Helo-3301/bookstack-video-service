"""Metrics and monitoring endpoints."""

import logging
import os
import platform
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bsvs.config import get_settings
from bsvs.db import get_db, Video, VideoVariant, TranscodeJob, VideoStatus, JobStatus

logger = logging.getLogger(__name__)
router = APIRouter()

# Track application start time
_start_time = time.time()


class SystemMetrics(BaseModel):
    """System-level metrics."""
    uptime_seconds: float
    python_version: str
    platform: str
    cpu_count: int
    pid: int


class VideoMetrics(BaseModel):
    """Video-related metrics."""
    total_videos: int
    videos_by_status: dict[str, int]
    total_variants: int
    total_storage_bytes: int


class JobMetrics(BaseModel):
    """Transcode job metrics."""
    total_jobs: int
    jobs_by_status: dict[str, int]
    active_jobs: int


class HealthStatus(BaseModel):
    """Detailed health status."""
    status: str
    version: str
    database: str
    redis: str
    storage: str
    uptime_seconds: float
    timestamp: str


class MetricsResponse(BaseModel):
    """Combined metrics response."""
    system: SystemMetrics
    videos: VideoMetrics
    jobs: JobMetrics
    timestamp: str


@router.get("/health", response_model=HealthStatus)
async def detailed_health(
    db: AsyncSession = Depends(get_db),
):
    """
    Detailed health check with component status.

    Returns health status of database, Redis, and storage.
    """
    settings = get_settings()
    status = "healthy"
    db_status = "healthy"
    redis_status = "unknown"
    storage_status = "healthy"

    # Check database
    try:
        await db.execute(select(func.count()).select_from(Video))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
        status = "degraded"

    # Check Redis (via Celery)
    try:
        from bsvs.worker.celery_app import celery_app
        celery_app.control.ping(timeout=1)
        redis_status = "healthy"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "unhealthy"
        # Redis being down doesn't make the service unhealthy
        # (uploads still work, just can't transcode)

    # Check storage
    if not settings.storage_path.exists():
        storage_status = "unhealthy"
        status = "degraded"

    return HealthStatus(
        status=status,
        version="0.1.0",
        database=db_status,
        redis=redis_status,
        storage=storage_status,
        uptime_seconds=time.time() - _start_time,
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
):
    """
    Get application metrics for monitoring.

    Returns video counts, job statistics, and system info.
    """
    settings = get_settings()

    # Video counts by status
    video_counts = {}
    for status in VideoStatus:
        result = await db.execute(
            select(func.count()).select_from(Video).where(Video.status == status.value)
        )
        video_counts[status.value] = result.scalar() or 0

    total_videos = sum(video_counts.values())

    # Variant counts and storage
    variant_result = await db.execute(
        select(
            func.count(VideoVariant.id),
            func.coalesce(func.sum(VideoVariant.file_size_bytes), 0)
        )
    )
    variant_row = variant_result.one()
    total_variants = variant_row[0] or 0
    total_storage = variant_row[1] or 0

    # Job counts by status
    job_counts = {}
    for status in JobStatus:
        result = await db.execute(
            select(func.count()).select_from(TranscodeJob).where(TranscodeJob.status == status.value)
        )
        job_counts[status.value] = result.scalar() or 0

    total_jobs = sum(job_counts.values())
    active_jobs = job_counts.get(JobStatus.PROCESSING.value, 0)

    return MetricsResponse(
        system=SystemMetrics(
            uptime_seconds=time.time() - _start_time,
            python_version=platform.python_version(),
            platform=platform.system(),
            cpu_count=os.cpu_count() or 1,
            pid=os.getpid(),
        ),
        videos=VideoMetrics(
            total_videos=total_videos,
            videos_by_status=video_counts,
            total_variants=total_variants,
            total_storage_bytes=total_storage,
        ),
        jobs=JobMetrics(
            total_jobs=total_jobs,
            jobs_by_status=job_counts,
            active_jobs=active_jobs,
        ),
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/prometheus")
async def prometheus_metrics(
    db: AsyncSession = Depends(get_db),
):
    """
    Export metrics in Prometheus format.

    Returns metrics in plain text format compatible with Prometheus scraping.
    """
    settings = get_settings()
    lines = []

    # Uptime
    lines.append(f"# HELP bsvs_uptime_seconds Application uptime in seconds")
    lines.append(f"# TYPE bsvs_uptime_seconds gauge")
    lines.append(f"bsvs_uptime_seconds {time.time() - _start_time:.2f}")

    # Video counts by status
    lines.append(f"# HELP bsvs_videos_total Total number of videos by status")
    lines.append(f"# TYPE bsvs_videos_total gauge")
    for status in VideoStatus:
        result = await db.execute(
            select(func.count()).select_from(Video).where(Video.status == status.value)
        )
        count = result.scalar() or 0
        lines.append(f'bsvs_videos_total{{status="{status.value}"}} {count}')

    # Variant count
    variant_result = await db.execute(
        select(
            func.count(VideoVariant.id),
            func.coalesce(func.sum(VideoVariant.file_size_bytes), 0)
        )
    )
    variant_row = variant_result.one()
    lines.append(f"# HELP bsvs_variants_total Total number of video variants")
    lines.append(f"# TYPE bsvs_variants_total gauge")
    lines.append(f"bsvs_variants_total {variant_row[0] or 0}")

    # Storage usage
    lines.append(f"# HELP bsvs_storage_bytes Total storage used in bytes")
    lines.append(f"# TYPE bsvs_storage_bytes gauge")
    lines.append(f"bsvs_storage_bytes {variant_row[1] or 0}")

    # Job counts by status
    lines.append(f"# HELP bsvs_jobs_total Total number of transcode jobs by status")
    lines.append(f"# TYPE bsvs_jobs_total gauge")
    for status in JobStatus:
        result = await db.execute(
            select(func.count()).select_from(TranscodeJob).where(TranscodeJob.status == status.value)
        )
        count = result.scalar() or 0
        lines.append(f'bsvs_jobs_total{{status="{status.value}"}} {count}')

    return "\n".join(lines) + "\n"
