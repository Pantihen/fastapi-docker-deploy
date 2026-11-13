import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.celery_app import celery_app
from app.dependencies import get_current_user
from app.models import User
from app.schemas import EmailRequest, Message, TaskQueued, TaskStatus
from app.tasks import send_email

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": Message, "description": "Нет токена или токен недействителен"}},
)


@router.post(
    "/send-email",
    response_model=TaskQueued,
    status_code=status.HTTP_202_ACCEPTED,
    responses={503: {"model": Message, "description": "Брокер задач (Redis) недоступен"}},
)
def queue_email(data: EmailRequest, current_user: User = Depends(get_current_user)) -> TaskQueued:
    """Ставит отправку письма в очередь и сразу отвечает 202 с id задачи.

    Если получатель не указан, письмо уходит на email текущего пользователя.
    """
    to = data.to or current_user.email
    try:
        task = send_email.delay(to, data.subject, data.body)
    except Exception:
        logger.exception("Не удалось поставить задачу в очередь")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Брокер задач недоступен, попробуйте позже",
        )
    return TaskQueued(task_id=task.id, status=task.status)


@router.get("/{task_id}", response_model=TaskStatus)
def get_task_status(task_id: str) -> TaskStatus:
    """Текущий статус задачи: PENDING → STARTED → SUCCESS (или FAILURE).

    Результат возвращается только когда задача завершилась успешно.
    Неизвестный id Celery тоже показывает как PENDING.
    """
    result = celery_app.AsyncResult(task_id)
    response = TaskStatus(task_id=task_id, status=result.status, ready=result.ready())
    if result.successful():
        response.result = result.result
    elif result.failed():
        response.error = str(result.result)
    return response
