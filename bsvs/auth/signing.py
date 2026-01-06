"""URL signing utilities for secure stream access."""

import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bsvs.config import get_settings


def _get_secret_key() -> bytes:
    """Get the secret key for signing."""
    settings = get_settings()
    return settings.secret_key.encode("utf-8")


def sign_url(
    url: str,
    expires_in: int = 3600,
    video_id: str | None = None,
) -> str:
    """
    Sign a URL with an expiring HMAC signature.

    Args:
        url: The URL to sign
        expires_in: Seconds until signature expires (default 1 hour)
        video_id: Optional video ID to include in signature

    Returns:
        URL with added signature and expiration parameters
    """
    expires_at = int(time.time()) + expires_in

    # Parse the URL
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # Add expiration
    query_params["exp"] = [str(expires_at)]
    if video_id:
        query_params["vid"] = [video_id]

    # Build the string to sign (path + sorted params without sig)
    params_to_sign = {k: v[0] for k, v in sorted(query_params.items())}
    sign_string = f"{parsed.path}?{urlencode(params_to_sign)}"

    # Generate HMAC signature
    signature = hmac.new(
        _get_secret_key(),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]  # Use first 32 chars for shorter URLs

    # Add signature to params
    query_params["sig"] = [signature]

    # Rebuild URL
    new_query = urlencode({k: v[0] for k, v in query_params.items()})
    signed_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))

    return signed_url


def verify_signature(url: str) -> tuple[bool, str | None]:
    """
    Verify a signed URL.

    Args:
        url: The signed URL to verify

    Returns:
        Tuple of (is_valid, error_message)
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # Extract signature
    sig = query_params.get("sig", [None])[0]
    if not sig:
        return False, "Missing signature"

    # Extract expiration
    exp = query_params.get("exp", [None])[0]
    if not exp:
        return False, "Missing expiration"

    try:
        expires_at = int(exp)
    except ValueError:
        return False, "Invalid expiration"

    # Check expiration
    if time.time() > expires_at:
        return False, "Signature expired"

    # Rebuild the string that was signed (without sig param)
    params_without_sig = {
        k: v[0] for k, v in sorted(query_params.items())
        if k != "sig"
    }
    sign_string = f"{parsed.path}?{urlencode(params_without_sig)}"

    # Verify signature
    expected_sig = hmac.new(
        _get_secret_key(),
        sign_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(sig, expected_sig):
        return False, "Invalid signature"

    return True, None


def generate_stream_token(
    video_id: str,
    expires_in: int = 3600,
) -> str:
    """
    Generate a token for stream access.

    This token can be passed as a query parameter to authenticate
    stream requests without signing each segment URL.

    Args:
        video_id: The video ID to authorize
        expires_in: Seconds until token expires

    Returns:
        Stream access token
    """
    expires_at = int(time.time()) + expires_in
    token_data = f"{video_id}:{expires_at}"

    signature = hmac.new(
        _get_secret_key(),
        token_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    # Token format: video_id:expires_at:signature
    return f"{video_id}:{expires_at}:{signature}"


def verify_stream_token(token: str) -> tuple[bool, str | None, str | None]:
    """
    Verify a stream access token.

    Args:
        token: The stream token to verify

    Returns:
        Tuple of (is_valid, video_id, error_message)
    """
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False, None, "Invalid token format"

        video_id, exp_str, signature = parts
        expires_at = int(exp_str)
    except (ValueError, AttributeError):
        return False, None, "Invalid token format"

    # Check expiration
    if time.time() > expires_at:
        return False, None, "Token expired"

    # Verify signature
    token_data = f"{video_id}:{exp_str}"
    expected_sig = hmac.new(
        _get_secret_key(),
        token_data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(signature, expected_sig):
        return False, None, "Invalid token"

    return True, video_id, None
