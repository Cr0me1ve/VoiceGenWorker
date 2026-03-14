from celery import Celery
from kombu import Queue
from worker.config import get_settings

settings = get_settings()

celery = Celery(
    "voicegen",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["worker.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
    result_expires=86400,
    task_queues=(
        Queue("voice"),
    ),
    task_default_queue="voice",
)
