"""Video streaming endpoints for HLS playback."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bsvs.config import get_settings
from bsvs.db import get_db, Video, VideoStatus
from bsvs.auth import verify_stream_token

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_token(video_id: str, token: str | None) -> None:
    """
    Validate stream token for video access.

    Raises HTTPException if token is invalid or expired.
    """
    settings = get_settings()

    # Skip validation in debug mode if no token provided
    if settings.debug and not token:
        logger.debug("Debug mode: skipping token validation")
        return

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Stream token required"
        )

    is_valid, token_video_id, error = verify_stream_token(token)

    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail=f"Invalid stream token: {error}"
        )

    if token_video_id != video_id:
        raise HTTPException(
            status_code=403,
            detail="Token does not match video"
        )


@router.get("/{video_id}/master.m3u8")
async def get_master_playlist(
    video_id: str,
    token: str | None = Query(None, description="Stream access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the master HLS playlist that references all quality variants.

    This is the main entry point for HLS playback.
    Requires a valid stream token for access.
    """
    validate_token(video_id, token)
    settings = get_settings()

    # Get video from database with eager-loaded variants
    result = await db.execute(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.variants))
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status != VideoStatus.READY.value:
        raise HTTPException(status_code=404, detail="Video not ready")

    # Build master playlist with token in variant URLs
    playlist_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

    for variant in sorted(video.variants, key=lambda v: v.height, reverse=True):
        # Add variant stream info
        bandwidth = variant.bitrate * 1000  # Convert kbps to bps
        resolution = f"{variant.width}x{variant.height}"
        playlist_lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}"
        )
        # Include token in variant playlist URL
        playlist_lines.append(f"{variant.quality}/playlist.m3u8?token={token}")

    playlist_content = "\n".join(playlist_lines)

    return Response(
        content=playlist_content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{video_id}/{quality}/playlist.m3u8")
async def get_variant_playlist(
    video_id: str,
    quality: str,
    token: str | None = Query(None, description="Stream access token"),
    db: AsyncSession = Depends(get_db),
):
    """Get the HLS playlist for a specific quality variant."""
    validate_token(video_id, token)
    settings = get_settings()

    # Verify video exists
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Find the playlist file
    playlist_path = settings.storage_path / video_id / "transcoded" / quality / "playlist.m3u8"

    if not playlist_path.exists():
        raise HTTPException(status_code=404, detail=f"Playlist not found for quality: {quality}")

    # Read and modify playlist to include token in segment URLs
    with open(playlist_path) as f:
        playlist_content = f.read()

    # Add token to segment URLs (.ts files)
    lines = []
    for line in playlist_content.split("\n"):
        if line.endswith(".ts"):
            lines.append(f"{line}?token={token}")
        else:
            lines.append(line)

    modified_playlist = "\n".join(lines)

    return Response(
        content=modified_playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{video_id}/{quality}/{segment}")
async def get_segment(
    video_id: str,
    quality: str,
    segment: str,
    token: str | None = Query(None, description="Stream access token"),
):
    """Get an HLS segment file (.ts)."""
    validate_token(video_id, token)
    settings = get_settings()

    # Validate segment filename (should be .ts file)
    if not segment.endswith(".ts"):
        raise HTTPException(status_code=400, detail="Invalid segment file")

    segment_path = settings.storage_path / video_id / "transcoded" / quality / segment

    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(
        segment_path,
        media_type="video/mp2t",
        headers={
            "Cache-Control": "max-age=31536000",  # Cache segments for 1 year
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{video_id}/thumbnail.jpg")
async def get_thumbnail(
    video_id: str,
    token: str | None = Query(None, description="Stream access token"),
):
    """Get the video thumbnail."""
    validate_token(video_id, token)
    settings = get_settings()

    # Try to find thumbnail
    thumb_path = settings.storage_path / video_id / "thumbnails" / "thumb_25.jpg"

    if not thumb_path.exists():
        # Try fallback
        thumb_path = settings.storage_path / video_id / "thumbnails" / "thumb_0.jpg"

    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{video_id}/subtitles/{subtitle_file}")
async def get_subtitle(
    video_id: str,
    subtitle_file: str,
    token: str | None = Query(None, description="Stream access token"),
):
    """Get a subtitle file (VTT format)."""
    validate_token(video_id, token)
    settings = get_settings()

    # Validate subtitle filename
    if not subtitle_file.endswith(".vtt"):
        raise HTTPException(status_code=400, detail="Invalid subtitle file format")

    subtitle_path = settings.storage_path / video_id / "subtitles" / subtitle_file

    if not subtitle_path.exists():
        raise HTTPException(status_code=404, detail="Subtitle not found")

    return FileResponse(
        subtitle_path,
        media_type="text/vtt",
        headers={
            "Cache-Control": "max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
