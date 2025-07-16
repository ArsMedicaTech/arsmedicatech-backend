"""
Celery worker configuration for ArsMedicaTech.
"""
import os

from celery import Celery  # type: ignore

from settings import REDIS_HOST, REDIS_PORT, UPLOADS_CHANNEL

# You can set these in your .env or settings.py
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{UPLOADS_CHANNEL}")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/{UPLOADS_CHANNEL}")


celery_app = Celery(
    "arsmedicatech",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
) 