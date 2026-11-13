import logging
import time
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="send_email", bind=True)
def send_email(self, to: str, subject: str, body: str) -> dict:
    """Имитация отправки письма: долгая операция, которая выполняется в воркере, а не в API."""
    started_at = datetime.now(timezone.utc)
    logger.info("[task %s] Отправка письма на %s: %r", self.request.id, to, subject)

    # Имитация обращения к SMTP-серверу
    time.sleep(settings.EMAIL_SEND_DELAY_SECONDS)

    finished_at = datetime.now(timezone.utc)
    logger.info("[task %s] Письмо на %s отправлено", self.request.id, to)
    return {
        "to": to,
        "subject": subject,
        "body_length": len(body),
        "sent": True,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
    }
