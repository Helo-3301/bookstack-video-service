"""Video embed player endpoint."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bsvs.config import get_settings
from bsvs.db import get_db, Video, VideoStatus
from bsvs.auth import generate_stream_token
from bsvs.bookstack import get_bookstack_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Templates directory
templates_dir = Path(__file__).parent.parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=templates_dir)


async def validate_bookstack_access(page_id: int | None) -> bool:
    """
    Validate that the viewer has access to the BookStack page.

    If page_id is None or BookStack is not configured, access is granted.
    """
    if page_id is None:
        return True

    client = get_bookstack_client()
    if not client.is_configured:
        logger.debug("BookStack not configured, skipping access check")
        return True

    try:
        has_access = await client.check_page_access(page_id)
        if not has_access:
            logger.warning(f"Access denied to BookStack page {page_id}")
        return has_access
    except Exception as e:
        logger.error(f"BookStack access check failed: {e}")
        # Fail open if BookStack is unreachable (configurable behavior)
        return True


@router.get("/{video_id}", response_class=HTMLResponse)
async def embed_player(
    request: Request,
    video_id: str,
    page_id: int | None = Query(None, description="BookStack page ID for access validation"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return an embeddable Video.js player for the specified video.

    This endpoint returns an HTML page with a Video.js player configured
    to play the HLS stream for the video.

    If page_id is provided, validates that the viewer has access to the
    corresponding BookStack page before serving the video.
    """
    settings = get_settings()

    # Validate BookStack page access if page_id provided
    if not await validate_bookstack_access(page_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied - you don't have permission to view this video"
        )

    # Get video from database with eager-loaded variants
    result = await db.execute(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.variants))
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check if video is ready
    if video.status != VideoStatus.READY.value:
        return templates.TemplateResponse(
            "processing.html",
            {
                "request": request,
                "video_id": video_id,
                "title": video.title,
                "status": video.status,
            },
        )

    # Get the best available variant
    variants = sorted(video.variants, key=lambda v: v.height, reverse=True)
    if not variants:
        raise HTTPException(status_code=404, detail="No video variants available")

    # Generate signed stream token (valid for 4 hours)
    stream_token = generate_stream_token(video_id, expires_in=14400)

    # Build signed stream URL
    stream_url = f"/stream/{video_id}/master.m3u8?token={stream_token}"
    poster_url = f"/stream/{video_id}/thumbnail.jpg?token={stream_token}"

    return templates.TemplateResponse(
        "player.html",
        {
            "request": request,
            "video_id": video_id,
            "title": video.title,
            "stream_url": stream_url,
            "poster_url": poster_url,
            "stream_token": stream_token,  # For JS to use in segment requests
            "variants": [
                {"quality": v.quality, "height": v.height}
                for v in variants
            ],
        },
    )
