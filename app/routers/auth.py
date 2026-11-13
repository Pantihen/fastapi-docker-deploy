import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Role, User
from app.rate_limit import limiter
from app.schemas import Message, RegisterOut, Token, UserCreate
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.tasks import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": Message, "description": "Email уже зарегистрирован"}},
)
def register(data: UserCreate, db: Session = Depends(get_db)) -> RegisterOut:
    email = data.email.lower()

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует")

    # Роль при самостоятельной регистрации всегда "user" — повысить может только admin
    user = User(email=email, hashed_password=hash_password(data.password), role=Role.user)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Гонка: два одновременных запроса с одним email — сработало уникальное ограничение БД
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже существует")
    db.refresh(user)

    # Приветственное письмо отправляется в фоне: ответ не ждёт окончания задачи
    task_id: str | None = None
    try:
        task_id = send_email.delay(
            user.email,
            "Добро пожаловать!",
            f"Здравствуйте, {user.email}! Регистрация прошла успешно.",
        ).id
    except Exception:  # брокер недоступен — регистрация всё равно считается успешной
        logger.exception("Не удалось поставить приветственное письмо в очередь")

    return RegisterOut.model_validate(user).model_copy(update={"welcome_email_task_id": task_id})


@router.post(
    "/login",
    response_model=Token,
    responses={
        401: {"model": Message, "description": "Неверный email или пароль"},
        429: {"description": "Слишком много попыток входа"},
    },
)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(
    request: Request,  # нужен slowapi для определения IP клиента
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Вход по email и паролю. В поле **username** формы передаётся email."""
    email = form_data.username.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    password_ok = verify_password(form_data.password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(access_token=token)
