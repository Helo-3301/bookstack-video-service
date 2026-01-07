"""Authentication endpoints for BookStack integration."""

import hashlib
import hmac
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsvs.config import get_settings
from bsvs.db import get_db, Video
from bsvs.bookstack import get_bookstack_client, BookStackUser

logger = logging.getLogger(__name__)
router = APIRouter()

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)


async def require_video_manager(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_bookstack_token: Annotated[str | None, Header()] = None,
) -> BookStackUser:
    """
    Dependency that requires a valid BookStack token with video management permissions.

    Accepts token via:
    - Authorization: Bearer <token_id:token_secret>
    - X-BookStack-Token: <token_id:token_secret>

    Raises:
        HTTPException 401: No token provided
        HTTPException 403: Token valid but user lacks Video Editor role
    """
    # Get token from header
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif x_bookstack_token:
        token = x_bookstack_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail="BookStack API token required. Use Authorization: Bearer <token_id:token_secret>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate against BookStack
    client = get_bookstack_client()
    if not client.base_url:
        raise HTTPException(
            status_code=503,
            detail="BookStack integration not configured",
        )

    user = await client.validate_user_token(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid BookStack API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check permissions
    if not user.can_manage_videos():
        raise HTTPException(
            status_code=403,
            detail="Access denied. Requires Admin or Video Editor role in BookStack.",
        )

    logger.info(f"Authenticated video manager: {user.name} ({user.email})")
    return user


async def optional_video_manager(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_bookstack_token: Annotated[str | None, Header()] = None,
) -> BookStackUser | None:
    """
    Optional authentication - returns user if valid token provided, None otherwise.
    Does not raise exceptions for missing/invalid tokens.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif x_bookstack_token:
        token = x_bookstack_token

    if not token:
        return None

    client = get_bookstack_client()
    if not client.base_url:
        return None

    user = await client.validate_user_token(token)
    if user and user.can_manage_videos():
        return user
    return None


class ViewerTokenRequest(BaseModel):
    """Request for a viewer token."""
    video_id: str
    page_id: int | None = None  # BookStack page ID if embedding in a page


class ViewerTokenResponse(BaseModel):
    """Response with viewer token."""
    token: str
    expires_at: int
    video_id: str


class PermissionCheckResponse(BaseModel):
    """Response for permission check."""
    allowed: bool
    reason: str | None = None


def generate_viewer_token(
    video_id: str,
    page_id: int | None = None,
    expires_in: int = 3600,
) -> tuple[str, int]:
    """
    Generate a viewer token for video access.

    The token proves the viewer was authorized at generation time.
    For page_protected videos, this should only be called after
    verifying the user has access to the associated page.

    Returns:
        Tuple of (token, expires_at_timestamp)
    """
    settings = get_settings()
    expires_at = int(time.time()) + expires_in

    # Token data includes video, optional page, and expiration
    token_data = f"viewer:{video_id}:{page_id or 'none'}:{expires_at}"

    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        token_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    # Token format: v1:video_id:page_id:expires_at:signature
    token = f"v1:{video_id}:{page_id or 'none'}:{expires_at}:{signature}"

    return token, expires_at


def verify_viewer_token(token: str, video_id: str) -> tuple[bool, int | None, str | None]:
    """
    Verify a viewer token.

    Args:
        token: The viewer token to verify
        video_id: The video ID being accessed

    Returns:
        Tuple of (is_valid, page_id, error_message)
    """
    settings = get_settings()

    try:
        parts = token.split(":")
        if len(parts) != 5 or parts[0] != "v1":
            return False, None, "Invalid token format"

        _, token_video_id, page_id_str, exp_str, signature = parts
        expires_at = int(exp_str)
        page_id = None if page_id_str == "none" else int(page_id_str)

    except (ValueError, AttributeError):
        return False, None, "Invalid token format"

    # Check video ID matches
    if token_video_id != video_id:
        return False, None, "Token video mismatch"

    # Check expiration
    if time.time() > expires_at:
        return False, None, "Token expired"

    # Verify signature
    token_data = f"viewer:{token_video_id}:{page_id_str}:{exp_str}"
    expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        token_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(signature, expected_sig):
        return False, None, "Invalid signature"

    return True, page_id, None


@router.post("/viewer-token", response_model=ViewerTokenResponse)
async def get_viewer_token(
    request: Request,
    body: ViewerTokenRequest,
    db: AsyncSession = Depends(get_db),
    x_bookstack_token: Annotated[str | None, Header()] = None,
):
    """
    Get a viewer token for video access.

    This endpoint is called by the BookStack plugin when a user views
    a page with an embedded video. The token proves the user was
    authorized to view the video at the time of generation.

    For page_protected videos, this will verify the page is accessible
    before issuing a token.
    """
    settings = get_settings()

    # Get video
    result = await db.execute(select(Video).where(Video.id == body.video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check video visibility
    visibility = video.visibility or "public"

    if visibility == "public":
        # Public videos - always allow
        token, expires_at = generate_viewer_token(body.video_id, body.page_id)
        return ViewerTokenResponse(
            token=token,
            expires_at=expires_at,
            video_id=body.video_id,
        )

    elif visibility == "unlisted":
        # Unlisted videos - allow if they know the video ID
        token, expires_at = generate_viewer_token(body.video_id, body.page_id)
        return ViewerTokenResponse(
            token=token,
            expires_at=expires_at,
            video_id=body.video_id,
        )

    elif visibility == "page_protected":
        # Page protected - must have page_id and it must be accessible
        if not body.page_id:
            raise HTTPException(
                status_code=403,
                detail="This video requires a page context"
            )

        # Verify page access via BookStack API
        client = get_bookstack_client()
        if not client.is_configured:
            logger.warning("BookStack not configured, allowing page_protected video")
            token, expires_at = generate_viewer_token(body.video_id, body.page_id)
            return ViewerTokenResponse(
                token=token,
                expires_at=expires_at,
                video_id=body.video_id,
            )

        try:
            # Check if the page is accessible
            # Note: This checks using BSVS's API token, not the user's session
            # For full user-level permissions, we'd need BookStack to validate
            has_access = await client.check_page_access(body.page_id)

            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="Page not accessible"
                )

            # Check if video is linked to this page
            if video.bookstack_page_id and video.bookstack_page_id != body.page_id:
                raise HTTPException(
                    status_code=403,
                    detail="Video is not available on this page"
                )

            token, expires_at = generate_viewer_token(body.video_id, body.page_id)
            return ViewerTokenResponse(
                token=token,
                expires_at=expires_at,
                video_id=body.video_id,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"BookStack permission check failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Permission check failed"
            )

    elif visibility == "private":
        # Private videos - require admin authentication
        # For now, reject all viewer token requests for private videos
        raise HTTPException(
            status_code=403,
            detail="This video is private"
        )

    else:
        # Unknown visibility - deny
        raise HTTPException(
            status_code=403,
            detail="Unknown visibility setting"
        )


class UserPermissionsResponse(BaseModel):
    """Response with user permissions."""
    authenticated: bool
    can_manage_videos: bool
    user_name: str | None = None
    user_email: str | None = None


@router.get("/me", response_model=UserPermissionsResponse)
async def get_current_user_permissions(
    user: BookStackUser | None = Depends(optional_video_manager),
):
    """
    Check current user's permissions for video management.

    Returns authentication status and whether user has Admin or Video Editor role.
    Used by the BookStack plugin to determine whether to show video management UI.
    """
    if user:
        return UserPermissionsResponse(
            authenticated=True,
            can_manage_videos=True,
            user_name=user.name,
            user_email=user.email,
        )
    return UserPermissionsResponse(
        authenticated=False,
        can_manage_videos=False,
    )


@router.get("/check-permission/{video_id}")
async def check_permission(
    video_id: str,
    page_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> PermissionCheckResponse:
    """
    Check if a video can be viewed in a given context.

    This is a lightweight check that doesn't generate a token.
    Useful for the plugin to decide whether to show the video option.
    """
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        return PermissionCheckResponse(allowed=False, reason="Video not found")

    visibility = video.visibility or "public"

    if visibility == "public":
        return PermissionCheckResponse(allowed=True)

    elif visibility == "unlisted":
        return PermissionCheckResponse(allowed=True)

    elif visibility == "page_protected":
        if not page_id:
            return PermissionCheckResponse(
                allowed=False,
                reason="Requires page context"
            )

        # Check if video is linked to this specific page
        if video.bookstack_page_id and video.bookstack_page_id != page_id:
            return PermissionCheckResponse(
                allowed=False,
                reason="Video not available on this page"
            )

        return PermissionCheckResponse(allowed=True)

    elif visibility == "private":
        return PermissionCheckResponse(
            allowed=False,
            reason="Video is private"
        )

    return PermissionCheckResponse(allowed=False, reason="Unknown visibility")
