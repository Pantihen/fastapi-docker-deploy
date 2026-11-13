"""Celery: постановка задачи через .delay() и проверка статуса.

В тестах включён task_always_eager, поэтому задача выполняется сразу.
Реальная асинхронность (PENDING → STARTED → SUCCESS в отдельном воркере) показана в README.
"""

from unittest.mock import patch

from app.tasks import send_email
from tests.test_api import USER, auth, register, token_for


def test_send_email_task_returns_result():
    result = send_email.delay("a@example.com", "Тема", "Текст")
    assert result.status == "SUCCESS"
    assert result.result["to"] == "a@example.com"
    assert result.result["sent"] is True


def test_endpoint_calls_delay(client):
    register(client)
    token = token_for(client, USER)
    with patch("app.routers.tasks.send_email.delay", wraps=send_email.delay) as delay:
        r = client.post("/tasks/send-email", json={"subject": "Привет"}, headers=auth(token))
    assert r.status_code == 202
    delay.assert_called_once()
    assert delay.call_args.args[0] == USER["email"]  # по умолчанию — текущий пользователь
    assert r.json()["task_id"]


def test_task_status_success_with_result(client):
    register(client)
    token = token_for(client, USER)
    task_id = client.post(
        "/tasks/send-email", json={"to": "x@example.com", "subject": "S"}, headers=auth(token)
    ).json()["task_id"]

    r = client.get(f"/tasks/{task_id}", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCESS"
    assert body["ready"] is True
    assert body["result"]["to"] == "x@example.com"


def test_task_status_pending_for_unknown_id(client):
    register(client)
    token = token_for(client, USER)
    r = client.get("/tasks/00000000-0000-0000-0000-000000000000", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["ready"] is False
    assert body["result"] is None


def test_register_queues_welcome_email(client):
    with patch("app.routers.auth.send_email.delay", wraps=send_email.delay) as delay:
        r = register(client)
    assert r.status_code == 201
    delay.assert_called_once()
    assert delay.call_args.args[0] == USER["email"]


def test_tasks_require_auth(client):
    assert client.post("/tasks/send-email", json={}).status_code == 401
    assert client.get("/tasks/some-id").status_code == 401
