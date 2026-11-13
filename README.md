# FastAPI App: Docker, CI/CD, деплой

FastAPI-приложение из прошлых разделов курса (JWT и роли, фоновые задачи Celery, GraphQL),
упакованное в Docker вместе с PostgreSQL и Redis. Тесты запускаются в GitHub Actions, приложение развёрнуто на Railway.

## 🌐 Публичный адрес

| | |
|---|---|
| Приложение | **https://ВАШ-АДРЕС.up.railway.app** |
| Swagger UI | https://ВАШ-АДРЕС.up.railway.app/docs |
| Health-check | https://ВАШ-АДРЕС.up.railway.app/health |
| GraphiQL | https://ВАШ-АДРЕС.up.railway.app/graphql |

> Замените `ВАШ-АДРЕС` на домен, который выдаст Railway (раздел «Деплой на Railway», шаг 5).

---

## Быстрый старт (Docker)

```bash
docker compose up --build
```

| URL | Что там |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | `{"status":"ok","database":"ok","database_backend":"postgresql","redis":"ok"}` |
| http://localhost:8000/graphql | GraphiQL |

Администратор создаётся при старте: `admin@example.com` / `Admin12345` (задаётся в `.env.docker`).

Остановить:

```bash
docker compose down        # с флагом -v удалятся и данные PostgreSQL
```

### Сервисы docker-compose.yml

| Сервис | Образ | Назначение |
|---|---|---|
| `app` | сборка из `Dockerfile` | FastAPI (uvicorn), порт 8000 |
| `db` | `postgres:16-alpine` | PostgreSQL, данные в volume `pgdata` |
| `redis` | `redis:7-alpine` | брокер и хранилище результатов Celery |
| `worker` | сборка из `Dockerfile` | Celery-воркер (`celery -A app.celery_app worker`) |

У каждого сервиса есть healthcheck. `app` запускается только после того, как `db` и `redis` станут
`healthy` (`depends_on: condition: service_healthy`), поэтому приложение не падает, пока
PostgreSQL ещё не готов. Порты `db` и `redis` наружу не публикуются: снаружи доступен только `app`.

### Почему в .env.docker имена сервисов, а не localhost

```env
DATABASE_URL=postgresql+psycopg://app:app_password@db:5432/app_db
CELERY_BROKER_URL=redis://redis:6379/0
```

Каждый контейнер — отдельная машина со своим сетевым стеком. `localhost` внутри контейнера `app`
указывает на сам `app`, а PostgreSQL там не запущен. Docker Compose создаёт общую сеть, в которой
встроенный DNS превращает имя сервиса (`db`, `redis`) в IP нужного контейнера.

Для запуска без Docker используется `.env.example` с `localhost`.

### Dockerfile

- база `python:3.12-slim`; зависимости ставятся отдельным слоем, чтобы кешировались при сборке;
- приложение запускается от непривилегированного пользователя `appuser`, а не от root;
- `HEALTHCHECK` обращается к `/health`;
- команда запуска:
  ```dockerfile
  CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
  ```
  - `--host 0.0.0.0` нужен, чтобы приложение слушало все интерфейсы. С `127.0.0.1` оно было бы недоступно снаружи контейнера.
  - `${PORT:-8000}`: Railway передаёт порт в переменной `PORT`, локально используется 8000.
  - `--proxy-headers` нужен, чтобы брать реальный IP клиента из `X-Forwarded-For`. Без этого флага rate limit `/auth/login` считал бы всех пользователей одним IP прокси хостинга.

---

## CI: GitHub Actions

Файл `.github/workflows/ci.yml` запускается при **push в `main`** и при pull request в `main`.

| Job | Что делает |
|---|---|
| `test` | поднимает PostgreSQL как service-контейнер, ставит зависимости и запускает `pytest -v` (33 теста) на настоящем PostgreSQL |
| `docker` | после успешных тестов выполняет `docker compose up --build --wait`, проверяет `/health` (БД и Redis `ok`) и `/docs`, затем `docker compose down` |

Результаты видны на вкладке **Actions** репозитория.

---

## Деплой на Railway

В репозитории есть `railway.json`: Railway собирает образ из `Dockerfile` и проверяет `/health` перед переключением трафика на новую версию.

1. **New Project → Deploy from GitHub repo** и выберите этот репозиторий. Railway найдёт `railway.json` и соберёт `Dockerfile`.
2. В проекте: **+ Create → Database → PostgreSQL**, затем **+ Create → Database → Redis**.
3. В сервисе приложения откройте **Variables** и добавьте:
   ```env
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   CELERY_BROKER_URL=${{Redis.REDIS_URL}}/0
   CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/1
   SECRET_KEY=<длинная случайная строка: python -c "import secrets; print(secrets.token_hex(32))">
   CORS_ORIGINS=https://ВАШ-АДРЕС.up.railway.app
   ADMIN_EMAIL=admin@example.com
   ADMIN_PASSWORD=<свой пароль>
   ```
   Конструкция `${{Postgres.DATABASE_URL}}` — ссылка на переменную другого сервиса Railway, и там тоже
   используется внутреннее имя сервиса, а не localhost. Адрес вида `postgresql://...` приложение
   само переводит в `postgresql+psycopg://...` (`app/config.py`).
4. *(необязательно, для фоновых задач)* **+ Create → GitHub Repo** с тем же репозиторием. Это второй сервис, воркер.
   В его **Settings → Config-as-code** укажите путь `railway.worker.json` и добавьте те же переменные.
5. В сервисе приложения: **Settings → Networking → Generate Domain**. Полученный адрес впишите в начало этого README и в `CORS_ORIGINS`.
6. Проверьте `https://ВАШ-АДРЕС.up.railway.app/docs` и `/health`.

Railway автоматически пересобирает проект при каждом push в `main`.

---

## Запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # SQLite + Redis на localhost
uvicorn app.main:app --reload
celery -A app.celery_app worker --loglevel=info      # во втором терминале
```

Тесты:

```bash
pytest -v                                              # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/test_db pytest -v   # PostgreSQL
```

## Структура

```
.github/workflows/ci.yml   CI: pytest на PostgreSQL + smoke-тест docker compose
Dockerfile                 образ приложения (тот же образ используется для воркера)
docker-compose.yml         app, worker, db (PostgreSQL), redis
.env.docker                переменные для compose — имена сервисов вместо localhost
.env.example               переменные для запуска без Docker
railway.json               деплой сервиса приложения на Railway
railway.worker.json        деплой Celery-воркера на Railway
app/
  main.py                  FastAPI, CORS, rate limiting, роутеры, GraphQL
  config.py                настройки; нормализация postgresql:// → postgresql+psycopg://
  database.py              SQLAlchemy engine (pool_pre_ping)
  routers/health.py        GET /health — проверка БД и Redis
  routers/auth.py          /auth/register, /auth/login
  routers/users.py         /users/me
  routers/admin.py         /admin/* (только admin)
  routers/tasks.py         /tasks/send-email, /tasks/{id} (Celery)
  gql/schema.py            GraphQL (strawberry)
  celery_app.py, tasks.py  Celery
tests/                     33 теста
postman_collection.json
```

## Эндпоинты

| Метод | Путь | Доступ |
|---|---|---|
| GET | `/health` | все |
| POST | `/auth/register` | все |
| POST | `/auth/login` | все, не чаще 5 раз в минуту |
| GET | `/users/me` | авторизованные |
| GET | `/admin/users` | admin |
| PATCH | `/admin/users/{id}/role` | admin |
| POST | `/tasks/send-email` | авторизованные |
| GET | `/tasks/{task_id}` | авторизованные |
| POST | `/graphql` | зависит от запроса |
