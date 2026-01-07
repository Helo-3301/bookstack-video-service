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
from bsvs.db import get_db, Video, VideoStatus, Subtitle
from bsvs.auth import generate_stream_token
from bsvs.bookstack import get_bookstack_client
from bsvs.api.routes.auth import verify_viewer_token

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
    viewer_token: str | None = Query(None, alias="vt", description="Viewer access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return an embeddable Video.js player for the specified video.

    This endpoint returns an HTML page with a Video.js player configured
    to play the HLS stream for the video.

    Access control:
    - Public videos: Always accessible
    - Unlisted videos: Accessible via direct link
    - Page-protected videos: Require valid viewer token with matching page_id
    - Private videos: Not accessible via embed

    The viewer_token (vt) parameter should be obtained from /api/auth/viewer-token.
    """
    settings = get_settings()

    # First, get the video to check its visibility
    result = await db.execute(
        select(Video)
        .where(Video.id == video_id)
        .options(selectinload(Video.variants), selectinload(Video.subtitles))
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    visibility = video.visibility or "public"

    # Check access based on visibility
    if visibility == "private":
        raise HTTPException(
            status_code=403,
            detail="This video is private"
        )

    elif visibility == "page_protected":
        # Require a valid viewer token for page-protected videos
        if not viewer_token:
            raise HTTPException(
                status_code=403,
                detail="Access denied - viewer token required"
            )

        is_valid, token_page_id, error = verify_viewer_token(viewer_token, video_id)
        if not is_valid:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied - {error}"
            )

        # If video is linked to a specific page, verify it matches
        if video.bookstack_page_id and token_page_id != video.bookstack_page_id:
            raise HTTPException(
                status_code=403,
                detail="Video not available in this context"
            )

    elif visibility == "unlisted":
        # Unlisted videos are accessible via direct link, no extra validation
        pass

    elif visibility == "public":
        # Public videos need no validation, but can optionally validate page access
        if page_id and not await validate_bookstack_access(page_id):
            logger.warning(f"Page {page_id} not accessible, but video is public")
            # Still allow for public videos

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

    # Build subtitle list with signed URLs
    subtitles = [
        {
            "url": f"/stream/{video_id}/subtitles/{sub.id}.vtt?token={stream_token}",
            "lang": sub.language,
            "label": sub.label,
            "default": sub.is_default,
        }
        for sub in video.subtitles
    ]

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
            "subtitles": subtitles,
        },
    )
