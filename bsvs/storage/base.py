"""Abstract storage interface for video files."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, AsyncIterator


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, path: str, file: BinaryIO) -> str:
        """
        Save a file to storage.

        Args:
            path: Relative path where file should be stored
            file: File-like object to save

        Returns:
            The full path/URL to the saved file
        """
        pass

    @abstractmethod
    async def save_from_path(self, dest_path: str, source_path: Path) -> str:
        """
        Save a file from a local path to storage.

        Args:
            dest_path: Relative destination path in storage
            source_path: Local file path to copy from

        Returns:
            The full path/URL to the saved file
        """
        pass

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """
        Get a file's contents from storage.

        Args:
            path: Relative path to the file

        Returns:
            File contents as bytes
        """
        pass

    @abstractmethod
    async def get_stream(self, path: str) -> AsyncIterator[bytes]:
        """
        Stream a file's contents from storage.

        Args:
            path: Relative path to the file

        Yields:
            Chunks of file data
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            path: Relative path to the file

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def delete_directory(self, path: str) -> int:
        """
        Delete a directory and all its contents.

        Args:
            path: Relative path to the directory

        Returns:
            Number of files deleted
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            path: Relative path to the file

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def list_files(self, prefix: str = "") -> list[str]:
        """
        List files in storage with optional prefix filter.

        Args:
            prefix: Optional path prefix to filter by

        Returns:
            List of file paths
        """
        pass

    @abstractmethod
    def get_local_path(self, path: str) -> Path | None:
        """
        Get local filesystem path if available.

        For local storage, returns the actual path.
        For remote storage (S3), returns None.

        Args:
            path: Relative path to the file

        Returns:
            Local Path object or None
        """
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Get a URL to access the file.

        For local storage, returns a relative path.
        For S3, can return a pre-signed URL.

        Args:
            path: Relative path to the file
            expires_in: URL expiration time in seconds (for S3)

        Returns:
            URL or path to access the file
        """
        pass
