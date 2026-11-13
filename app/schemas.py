from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72, description="От 8 до 72 символов (ограничение bcrypt)")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
    created_at: datetime


class RoleUpdate(BaseModel):
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    detail: str


class RegisterOut(UserOut):
    welcome_email_task_id: str | None = Field(default=None,description="id фоновой задачи отправки приветственного письма")


class EmailRequest(BaseModel):
    to: EmailStr | None = Field(default=None, description="Получатель; по умолчанию — текущий пользователь")
    subject: str = Field(default="Тестовое письмо", max_length=200)
    body: str = Field(default="Привет! Это письмо отправлено фоновой задачей Celery.", max_length=5000)


class TaskQueued(BaseModel):
    task_id: str
    status: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    ready: bool
    result: Any | None = None
    error: str | None = None
