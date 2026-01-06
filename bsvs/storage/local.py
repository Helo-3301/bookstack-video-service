"""Local filesystem storage backend."""

import shutil
from pathlib import Path
from typing import BinaryIO, AsyncIterator

import aiofiles
import aiofiles.os

from bsvs.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """Local filesystem storage implementation."""

    def __init__(self, base_path: Path):
        """
        Initialize local storage.

        Args:
            base_path: Base directory for all stored files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _full_path(self, path: str) -> Path:
        """Get full filesystem path for a relative path."""
        return self.base_path / path

    async def save(self, path: str, file: BinaryIO) -> str:
        """Save a file to local storage."""
        full_path = self._full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, 'wb') as f:
            # Read in chunks for large files
            while chunk := file.read(8192):
                await f.write(chunk)

        return str(full_path)

    async def save_from_path(self, dest_path: str, source_path: Path) -> str:
        """Copy a file from local path to storage."""
        full_path = self._full_path(dest_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Use sync copy for efficiency (shutil is optimized)
        shutil.copy2(source_path, full_path)

        return str(full_path)

    async def get(self, path: str) -> bytes:
        """Get file contents from local storage."""
        full_path = self._full_path(path)
        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()

    async def get_stream(self, path: str) -> AsyncIterator[bytes]:
        """Stream file contents from local storage."""
        full_path = self._full_path(path)
        async with aiofiles.open(full_path, 'rb') as f:
            while chunk := await f.read(8192):
                yield chunk

    async def delete(self, path: str) -> bool:
        """Delete a file from local storage."""
        full_path = self._full_path(path)
        try:
            await aiofiles.os.remove(full_path)
            return True
        except FileNotFoundError:
            return False

    async def delete_directory(self, path: str) -> int:
        """Delete a directory and all its contents."""
        full_path = self._full_path(path)
        if not full_path.exists():
            return 0

        # Count files before deletion
        count = sum(1 for _ in full_path.rglob('*') if _.is_file())

        # Use sync rmtree (it's efficient)
        shutil.rmtree(full_path)

        return count

    async def exists(self, path: str) -> bool:
        """Check if a file exists in local storage."""
        full_path = self._full_path(path)
        return full_path.exists()

    async def list_files(self, prefix: str = "") -> list[str]:
        """List files in local storage."""
        search_path = self._full_path(prefix) if prefix else self.base_path

        if not search_path.exists():
            return []

        files = []
        for file_path in search_path.rglob('*'):
            if file_path.is_file():
                # Return path relative to base
                rel_path = file_path.relative_to(self.base_path)
                files.append(str(rel_path))

        return files

    def get_local_path(self, path: str) -> Path | None:
        """Get local filesystem path."""
        return self._full_path(path)

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get URL for local file (returns relative path)."""
        # For local storage, we return a path that can be used with
        # the streaming endpoint
        return f"/stream/{path}"
