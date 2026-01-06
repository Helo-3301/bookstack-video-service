"""Storage backends for video files."""

import logging
from functools import lru_cache

from bsvs.config import get_settings
from bsvs.storage.base import StorageBackend
from bsvs.storage.local import LocalStorage

logger = logging.getLogger(__name__)

__all__ = [
    "StorageBackend",
    "LocalStorage",
    "get_storage",
]


@lru_cache
def get_storage() -> StorageBackend:
    """
    Get the configured storage backend.

    Returns LocalStorage or S3Storage based on BSVS_STORAGE_TYPE setting.
    """
    settings = get_settings()

    if settings.storage_type == "s3":
        # Import S3 storage only when needed (requires boto3)
        try:
            from bsvs.storage.s3 import S3Storage
        except ImportError as e:
            logger.error(f"S3 storage requested but boto3 not installed: {e}")
            raise ImportError(
                "S3 storage requires boto3. Install with: pip install 'bsvs[s3]'"
            ) from e

        if not settings.s3_bucket:
            raise ValueError("BSVS_S3_BUCKET is required for S3 storage")

        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )

    # Default to local storage
    logger.info(f"Using local storage at: {settings.storage_path}")
    return LocalStorage(settings.storage_path)
