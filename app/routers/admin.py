from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import Role, User
from app.schemas import Message, RoleUpdate, UserOut

# Все эндпоинты роутера доступны только роли admin
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.admin))],
    responses={
        401: {"model": Message, "description": "Нет токена или токен недействителен"},
        403: {"model": Message, "description": "Недостаточно прав (нужна роль admin)"},
    },
)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    """Список всех пользователей — только для администратора."""
    return list(db.execute(select(User).order_by(User.id)).scalars().all())


@router.patch(
    "/users/{user_id}/role",
    response_model=UserOut,
    responses={404: {"model": Message, "description": "Пользователь не найден"}},
)
def change_role(user_id: int, data: RoleUpdate, db: Session = Depends(get_db)) -> User:
    """Изменить роль пользователя — только для администратора."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user
