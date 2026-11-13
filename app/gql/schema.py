"""GraphQL-схема (strawberry) для сущности User.

Клиент сам выбирает, какие поля получить: один и тот же запрос `users`
может вернуть только email или полный профиль — сервер отдаёт ровно запрошенное.
"""

from datetime import datetime
from typing import Any

import strawberry
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from strawberry.fastapi import BaseContext, GraphQLRouter
from strawberry.permission import BasePermission
from strawberry.types import Info

from app.database import get_db
from app.dependencies import get_optional_user
from app.models import Role, User

# ---------- Контекст: сессия БД и пользователь из JWT ----------


class Context(BaseContext):
    def __init__(self, db: Session, user: User | None) -> None:
        super().__init__()
        self.db = db
        self.user = user


def get_context(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Context:
    return Context(db=db, user=user)


# ---------- Права доступа ----------


class IsAuthenticated(BasePermission):
    message = "Требуется авторизация: передайте заголовок Authorization: Bearer <token>"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        return info.context.user is not None


class IsAdmin(BasePermission):
    message = "Недостаточно прав: нужна роль admin"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user = info.context.user
        return user is not None and user.role == Role.admin


# ---------- Типы ----------

RoleEnum = strawberry.enum(Role, name="Role", description="Роль пользователя")


@strawberry.type(name="User", description="Пользователь системы")
class UserType:
    id: int
    email: str
    role: RoleEnum
    created_at: datetime

    @classmethod
    def from_model(cls, user: User) -> "UserType":
        return cls(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


@strawberry.type(description="Статистика пользователей")
class UsersStats:
    total: int
    admins: int
    users: int


# ---------- Запросы ----------


@strawberry.type
class Query:
    @strawberry.field(description="Текущий пользователь (по JWT)", permission_classes=[IsAuthenticated])
    def me(self, info: Info) -> UserType:
        return UserType.from_model(info.context.user)

    @strawberry.field(description="Список пользователей (только admin)", permission_classes=[IsAdmin])
    def users(
        self,
        info: Info,
        role: RoleEnum | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[UserType]:
        db: Session = info.context.db
        stmt = select(User).order_by(User.id).limit(min(max(limit, 1), 100)).offset(max(offset, 0))
        if role is not None:
            stmt = stmt.where(User.role == role)
        return [UserType.from_model(u) for u in db.execute(stmt).scalars()]

    @strawberry.field(description="Пользователь по id (только admin)", permission_classes=[IsAdmin])
    def user(self, info: Info, id: int) -> UserType | None:
        user = info.context.db.get(User, id)
        return UserType.from_model(user) if user else None

    @strawberry.field(description="Сколько всего пользователей и админов (только admin)", permission_classes=[IsAdmin])
    def users_stats(self, info: Info) -> UsersStats:
        db: Session = info.context.db
        rows = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
        admins, users = rows.get(Role.admin, 0), rows.get(Role.user, 0)
        return UsersStats(total=admins + users, admins=admins, users=users)


schema = strawberry.Schema(query=Query)

graphql_router = GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql")
