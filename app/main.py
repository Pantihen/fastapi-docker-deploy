from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Role, User
from app.rate_limit import limiter
from app.gql.schema import graphql_router
from app.routers import admin, auth, health, tasks, users
from app.security import hash_password


def seed_admin() -> None:
    """Создаёт администратора из переменных окружения, если его ещё нет."""
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
    email = settings.ADMIN_EMAIL.lower()
    with SessionLocal() as db:
        exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if exists is None:
            db.add(User(email=email, hashed_password=hash_password(settings.ADMIN_PASSWORD), role=Role.admin))
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_admin()
    yield


app = FastAPI(
    title="FastAPI App",
    description=(
        "JWT-аутентификация и роли, фоновые задачи Celery (`/tasks`), GraphQL (`/graphql`). "
        "PostgreSQL + Redis, Docker, CI/CD."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

# Rate limiting (slowapi): 429 при превышении лимита
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS только для явно указанных origin (wildcard запрещён валидатором в config.py)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(tasks.router)
app.include_router(graphql_router, prefix="/graphql", tags=["graphql"])


@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "docs": "/docs", "graphql": "/graphql", "health": "/health"}
