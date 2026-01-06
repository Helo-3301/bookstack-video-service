"""Transcoding task (runs in background or via Celery)."""

import logging
from datetime import datetime
from pathlib import Path

from bsvs.config import get_settings
from bsvs.db.models import VideoStatus, JobStatus
from bsvs.transcode.ffmpeg import probe_video, transcode_to_hls, extract_thumbnails
from bsvs.transcode.presets import get_applicable_presets

logger = logging.getLogger(__name__)


def transcode_video(video_id: str, input_path: str):
    """
    Transcode a video to HLS format.

    This function runs synchronously and is designed to be called
    from a background task or Celery worker.

    Args:
        video_id: The video's database ID
        input_path: Path to the original video file
    """
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    settings = get_settings()
    logger.info(f"Starting transcode for video {video_id}")

    # Create a new database session for this background task
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async def _do_transcode():
        from bsvs.db.models import Video, VideoVariant, TranscodeJob

        async with async_session() as db:
            # Get video record
            result = await db.execute(select(Video).where(Video.id == video_id))
            video = result.scalar_one_or_none()

            if not video:
                logger.error(f"Video {video_id} not found")
                return

            # Create transcode job
            job = TranscodeJob(
                video_id=video_id,
                status=JobStatus.PROCESSING.value,
                started_at=datetime.utcnow(),
            )
            db.add(job)

            # Update video status
            video.status = VideoStatus.PROCESSING.value
            await db.commit()

            try:
                # Probe the video
                info = probe_video(input_path)
                video.duration_seconds = int(info.duration_seconds)
                logger.info(f"Video info: {info.width}x{info.height}, {info.duration_seconds}s")

                # Determine which presets to use
                presets = get_applicable_presets(
                    source_height=info.height,
                    requested=settings.presets_list,
                )
                logger.info(f"Using presets: {[p.name for p in presets]}")

                # Output directory
                output_dir = settings.storage_path / video_id / "transcoded"

                # Transcode each quality level
                for i, preset in enumerate(presets):
                    job.progress = int((i / len(presets)) * 80)
                    await db.commit()

                    logger.info(f"Transcoding to {preset.name}...")
                    playlist_path = transcode_to_hls(
                        input_path=input_path,
                        output_dir=output_dir,
                        preset=preset,
                    )

                    # Calculate file size
                    quality_dir = output_dir / preset.name
                    total_size = sum(f.stat().st_size for f in quality_dir.iterdir())

                    # Calculate width from height
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
                    db.add(variant)

                # Extract thumbnails
                job.progress = 90
                await db.commit()

                thumb_dir = settings.storage_path / video_id / "thumbnails"
                extract_thumbnails(input_path, thumb_dir)

                # Mark as complete
                job.status = JobStatus.COMPLETED.value
                job.progress = 100
                job.completed_at = datetime.utcnow()
                video.status = VideoStatus.READY.value

                await db.commit()
                logger.info(f"Transcode complete for video {video_id}")

            except Exception as e:
                logger.exception(f"Transcode failed for video {video_id}")
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                video.status = VideoStatus.FAILED.value
                await db.commit()

    # Run the async function
    asyncio.run(_do_transcode())
