from celery import Celery

from app.config import settings

celery_app = Celery(
    "advanced_api",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Показывать статус STARTED, пока задача выполняется в воркере
    task_track_started=True,
    # Хранить результаты сутки
    result_expires=60 * 60 * 24,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_store_eager_result=True,
    broker_connection_retry_on_startup=True,
)
