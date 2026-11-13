import os
import tempfile

# Отдельная БД для тестов — задаётся до импорта приложения.
# В CI передаётся TEST_DATABASE_URL с PostgreSQL, локально по умолчанию — временный SQLite.
_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{os.path.join(_tmp_dir, 'test.db')}"
)
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "Admin12345"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
# Celery в тестах: без Redis и воркера, задачи выполняются сразу, результат хранится в памяти
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["EMAIL_SEND_DELAY_SECONDS"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import limiter  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    limiter.reset()
    with TestClient(app) as c:  # lifespan: создаёт таблицы и админа
        yield c
