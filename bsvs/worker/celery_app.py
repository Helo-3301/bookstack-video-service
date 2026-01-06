"""Celery application configuration."""

from celery import Celery

from bsvs.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "bsvs",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["bsvs.worker.tasks"],
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time for transcoding

    # Result backend
    result_expires=3600,  # Results expire after 1 hour

    # Task routing
    task_routes={
        "bsvs.worker.tasks.transcode_video_task": {"queue": "transcode"},
    },

    # Default queue
    task_default_queue="default",
)
