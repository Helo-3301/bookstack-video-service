"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bsvs.db.base import Base


class VideoStatus(str, Enum):
    """Video processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobStatus(str, Enum):
    """Transcode job status."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class Video(Base):
    """Video metadata model."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=VideoStatus.PENDING.value)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # BookStack integration
    bookstack_page_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bookstack_uploader_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(String(50), default="inherit")

    # Relationships
    variants: Mapped[list["VideoVariant"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["TranscodeJob"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    subtitles: Mapped[list["Subtitle"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class VideoVariant(Base):
    """Transcoded video variant (different quality levels)."""

    __tablename__ = "video_variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"))
    quality: Mapped[str] = mapped_column(String(50))  # 1080p, 720p, 480p
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bitrate: Mapped[int] = mapped_column(Integer)  # kbps
    file_path: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)

    # Relationships
    video: Mapped["Video"] = relationship(back_populates="variants")


class TranscodeJob(Base):
    """Transcode job tracking."""

    __tablename__ = "transcode_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"))
    status: Mapped[str] = mapped_column(String(50), default=JobStatus.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    video: Mapped["Video"] = relationship(back_populates="jobs")


class Subtitle(Base):
    """Subtitle/caption track for a video."""

    __tablename__ = "subtitles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"))
    language: Mapped[str] = mapped_column(String(10))  # e.g., "en", "es", "fr"
    label: Mapped[str] = mapped_column(String(100))  # e.g., "English", "Spanish"
    file_path: Mapped[str] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    video: Mapped["Video"] = relationship(back_populates="subtitles")
