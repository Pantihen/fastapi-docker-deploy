"""Все сценарии из «Требований к демонстрации»."""

USER = {"email": "user@example.com", "password": "Password123"}
ADMIN = {"email": "admin@example.com", "password": "Admin12345"}


def register(client, data=USER):
    return client.post("/auth/register", json=data)


def login(client, email, password):
    # OAuth2PasswordRequestForm: form-data, email передаётся в поле username
    return client.post("/auth/login", data={"username": email, "password": password})


def token_for(client, creds):
    r = login(client, creds["email"], creds["password"])
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# 1. Успешная регистрация
def test_register_success(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == USER["email"]
    assert body["role"] == "user"
    assert "password" not in body and "hashed_password" not in body
    assert body["welcome_email_task_id"]  # приветственное письмо поставлено в очередь


def test_password_is_hashed(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    register(client)
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == USER["email"])).scalar_one()
    assert user.hashed_password != USER["password"]
    assert user.hashed_password.startswith("$2b$")  # bcrypt


# 2. Повторная регистрация с тем же email -> 409
def test_register_duplicate_email_409(client):
    assert register(client).status_code == 201
    r = register(client, {"email": "USER@example.com", "password": "Another123"})
    assert r.status_code == 409


# 3. Вход с получением токена
def test_login_returns_jwt(client):
    register(client)
    r = login(client, USER["email"], USER["password"])
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2  # header.payload.signature


def test_login_wrong_password_401(client):
    register(client)
    assert login(client, USER["email"], "wrong-password").status_code == 401


# 4. Защищённый эндпоинт с токеном и без
def test_protected_with_token_200(client):
    register(client)
    r = client.get("/users/me", headers=auth(token_for(client, USER)))
    assert r.status_code == 200
    assert r.json()["email"] == USER["email"]


def test_protected_without_token_401(client):
    assert client.get("/users/me").status_code == 401


def test_protected_with_invalid_token_401(client):
    assert client.get("/users/me", headers=auth("not.a.valid-token")).status_code == 401


def test_protected_with_expired_token_401(client):
    from app.security import create_access_token

    expired = create_access_token(subject="1", role="user", expires_minutes=-1)
    assert client.get("/users/me", headers=auth(expired)).status_code == 401


# 5. Admin-эндпоинт: user -> 403, admin -> 200
def test_admin_endpoint_as_user_403(client):
    register(client)
    r = client.get("/admin/users", headers=auth(token_for(client, USER)))
    assert r.status_code == 403


def test_admin_endpoint_as_admin_200(client):
    register(client)
    r = client.get("/admin/users", headers=auth(token_for(client, ADMIN)))
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {USER["email"], ADMIN["email"]} <= emails


def test_admin_endpoint_without_token_401(client):
    assert client.get("/admin/users").status_code == 401


def test_admin_can_change_role(client):
    user_id = register(client).json()["id"]
    r = client.patch(f"/admin/users/{user_id}/role", json={"role": "admin"}, headers=auth(token_for(client, ADMIN)))
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


# 6. Rate limit: шестая попытка входа подряд -> 429
def test_login_rate_limit_429(client):
    register(client)
    codes = [login(client, USER["email"], "wrong-password").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


# 7. CORS: разрешён только явно указанный origin
def test_cors_allowed_origin(client):
    r = client.options(
        "/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_foreign_origin_rejected(client):
    r = client.options(
        "/auth/login",
        headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_wildcard_forbidden():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="*")


# 8. SQL-инъекция не срабатывает (ORM, параметризованные запросы)
def test_sql_injection_in_login(client):
    register(client)
    r = login(client, "' OR '1'='1", "' OR '1'='1")
    assert r.status_code == 401


# Health-check: приложение отвечает и подключено к БД
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_postgres_url_normalized():
    from app.config import Settings

    s = Settings(DATABASE_URL="postgresql://u:p@db:5432/app")
    assert s.DATABASE_URL == "postgresql+psycopg://u:p@db:5432/app"
    assert Settings(DATABASE_URL="postgres://u:p@h/x").DATABASE_URL.startswith("postgresql+psycopg://")


def test_render_url_added_to_cors():
    from app.config import Settings

    s = Settings(CORS_ORIGINS="http://localhost:3000", RENDER_EXTERNAL_URL="https://app.onrender.com/")
    assert s.cors_origins_list == ["http://localhost:3000", "https://app.onrender.com"]
    assert Settings(CORS_ORIGINS="http://localhost:3000").cors_origins_list == ["http://localhost:3000"]
