from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models import User
from app.schemas import Message, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserOut,
    responses={401: {"model": Message, "description": "Нет токена или токен недействителен"}},
)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Защищённый эндпоинт: доступен любому авторизованному пользователю."""
    return current_user
