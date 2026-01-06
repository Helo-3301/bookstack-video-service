"""Rate limiting configuration for BSVS API."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from bsvs.config import get_settings


def _get_limiter_key(request):
    """
    Get rate limit key from request.

    Uses X-Forwarded-For header if behind a proxy, otherwise uses remote address.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Get first IP in chain (original client)
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Create limiter instance
# Uses memory storage by default, Redis in production
settings = get_settings()

# Use Redis if available, otherwise in-memory
if settings.redis_url and not settings.debug:
    storage_uri = settings.redis_url
else:
    storage_uri = "memory://"

limiter = Limiter(
    key_func=_get_limiter_key,
    storage_uri=storage_uri,
    default_limits=["200/minute"],  # Default rate limit
)

# Rate limit strings for common scenarios
# Usage: @limiter.limit(RATE_LIMIT_UPLOAD) on route functions

RATE_LIMIT_UPLOAD = "10/minute"      # Upload: stricter (expensive operation)
RATE_LIMIT_API_READ = "100/minute"   # API reads: moderate
RATE_LIMIT_STREAM = "500/minute"     # Streaming: higher (per-segment)
RATE_LIMIT_EMBED = "60/minute"       # Embed player: moderate
