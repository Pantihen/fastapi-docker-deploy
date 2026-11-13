from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User
from app.security import decode_access_token

# auto_error=False — чтобы самим вернуть 401 с понятным сообщением при отсутствии токена
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Проверяет JWT и возвращает пользователя. 401 — если токена нет или он недействителен."""
    if not token:
        raise _unauthorized("Не передан токен авторизации")

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _unauthorized("Недействительный или просроченный токен")

    # ORM-запрос: значение передаётся как параметр, а не подставляется в SQL-строку
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise _unauthorized("Пользователь из токена не найден")
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Как get_current_user, но без ошибки: None, если токена нет или он недействителен.
    Используется в GraphQL, где отказ в доступе возвращается в поле errors, а не HTTP-кодом."""
    try:
        return get_current_user(token=token, db=db)
    except HTTPException:
        return None


def require_role(*allowed_roles: Role) -> Callable[..., User]:
    """Фабрика зависимостей: пропускает только пользователей с одной из указанных ролей (иначе 403)."""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return current_user

    return role_checker
