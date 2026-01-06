"""BSVS Configuration using Pydantic Settings."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="BSVS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Core
    port: int = 8080
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/bsvs.db"

    # Storage
    storage_type: str = "local"  # local or s3
    storage_path: Path = Path("./data/videos")

    # S3 (optional)
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Transcoding
    transcode_workers: int = 2
    transcode_presets: str = "720p"  # comma-separated: 1080p,720p,480p
    max_upload_size_mb: int = 2048

    # Redis (for Celery)
    redis_url: str = "redis://localhost:6379/0"

    # BookStack Integration
    bookstack_url: str | None = None
    bookstack_token_id: str | None = None
    bookstack_token_secret: str | None = None

    @property
    def presets_list(self) -> list[str]:
        """Get transcoding presets as a list."""
        return [p.strip() for p in self.transcode_presets.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
