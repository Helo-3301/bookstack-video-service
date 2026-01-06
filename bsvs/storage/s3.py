"""S3-compatible storage backend."""

import logging
from pathlib import Path
from typing import BinaryIO, AsyncIterator

from bsvs.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class S3Storage(StorageBackend):
    """
    S3-compatible storage implementation.

    Supports AWS S3, MinIO, Backblaze B2, and other S3-compatible services.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        prefix: str = "",
    ):
        """
        Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            endpoint_url: Custom endpoint URL (for MinIO, B2, etc.)
            access_key: AWS access key ID
            secret_key: AWS secret access key
            region: AWS region (default: us-east-1)
            prefix: Optional prefix for all keys
        """
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install with: pip install 'bsvs[s3]'"
            )

        self.bucket = bucket
        self.prefix = prefix.strip("/")

        # Configure boto3 client
        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'}  # Required for some S3-compatible services
        )

        client_kwargs = {
            "config": config,
            "region_name": region,
        }

        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        self._client = boto3.client('s3', **client_kwargs)
        self._resource = boto3.resource('s3', **client_kwargs)
        self._bucket = self._resource.Bucket(bucket)

        logger.info(f"S3 storage initialized: bucket={bucket}, endpoint={endpoint_url}")

    def _full_key(self, path: str) -> str:
        """Get full S3 key for a relative path."""
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path

    async def save(self, path: str, file: BinaryIO) -> str:
        """Save a file to S3."""
        key = self._full_key(path)
        self._client.upload_fileobj(file, self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    async def save_from_path(self, dest_path: str, source_path: Path) -> str:
        """Upload a local file to S3."""
        key = self._full_key(dest_path)
        self._client.upload_file(str(source_path), self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    async def get(self, path: str) -> bytes:
        """Download a file from S3."""
        key = self._full_key(path)
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response['Body'].read()

    async def get_stream(self, path: str) -> AsyncIterator[bytes]:
        """Stream a file from S3."""
        key = self._full_key(path)
        response = self._client.get_object(Bucket=self.bucket, Key=key)

        # Stream in chunks
        body = response['Body']
        while chunk := body.read(8192):
            yield chunk

    async def delete(self, path: str) -> bool:
        """Delete a file from S3."""
        key = self._full_key(path)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete {key}: {e}")
            return False

    async def delete_directory(self, path: str) -> int:
        """Delete all objects with a given prefix."""
        prefix = self._full_key(path)
        if not prefix.endswith('/'):
            prefix += '/'

        # List and delete objects
        objects_to_delete = []
        paginator = self._client.get_paginator('list_objects_v2')

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                objects_to_delete.append({'Key': obj['Key']})

        if not objects_to_delete:
            return 0

        # Delete in batches of 1000 (S3 limit)
        deleted = 0
        for i in range(0, len(objects_to_delete), 1000):
            batch = objects_to_delete[i:i + 1000]
            self._client.delete_objects(
                Bucket=self.bucket,
                Delete={'Objects': batch}
            )
            deleted += len(batch)

        return deleted

    async def exists(self, path: str) -> bool:
        """Check if a file exists in S3."""
        key = self._full_key(path)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    async def list_files(self, prefix: str = "") -> list[str]:
        """List files in S3 with optional prefix."""
        full_prefix = self._full_key(prefix) if prefix else self.prefix

        files = []
        paginator = self._client.get_paginator('list_objects_v2')

        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Remove our prefix to get relative path
                if self.prefix and key.startswith(self.prefix + '/'):
                    key = key[len(self.prefix) + 1:]
                files.append(key)

        return files

    def get_local_path(self, path: str) -> Path | None:
        """S3 storage has no local path."""
        return None

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Generate a pre-signed URL for S3 object."""
        key = self._full_key(path)
        url = self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=expires_in
        )
        return url
