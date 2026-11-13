# FastAPI App: Docker, CI/CD, деплой

FastAPI-приложение из прошлых разделов курса (JWT и роли, фоновые задачи Celery, GraphQL),
упакованное в Docker вместе с PostgreSQL и Redis. Тесты запускаются в GitHub Actions, приложение развёрнуто на Render.

## 🌐 Публичный адрес

| | |
|---|---|
| Приложение | **https://ВАШ-АДРЕС.onrender.com** |
| Swagger UI | https://ВАШ-АДРЕС.onrender.com/docs |
| Health-check | https://ВАШ-АДРЕС.onrender.com/health |
| GraphiQL | https://ВАШ-АДРЕС.onrender.com/graphql |
| CI | https://github.com/Pantihen/fastapi-docker-deploy/actions |

> Приложение работает на бесплатном тарифе Render и засыпает после 15 минут без запросов.
> Первое открытие после простоя занимает около минуты, дальше всё работает быстро.

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
  - `${PORT:-8000}`: хостинг (Render) передаёт порт в переменной `PORT`, локально используется 8000.
  - `--proxy-headers` нужен, чтобы брать реальный IP клиента из `X-Forwarded-For`. Без этого флага rate limit `/auth/login` считал бы всех пользователей одним IP прокси хостинга.

---

## CI: GitHub Actions

Файл `.github/workflows/ci.yml` запускается при **push в `main`** и при pull request в `main`.

| Job | Что делает |
|---|---|
| `test` | поднимает PostgreSQL как service-контейнер, ставит зависимости и запускает `pytest -v` (35 тестов) на настоящем PostgreSQL |
| `docker` | после успешных тестов выполняет `docker compose up --build --wait`, проверяет `/health` (БД и Redis `ok`) и `/docs`, затем `docker compose down` |

Результаты видны на вкладке **Actions** репозитория.

---

## Деплой на Render

Деплой описан как код в `render.yaml` (Render Blueprint). Все ресурсы на бесплатном тарифе в регионе Frankfurt:

| Ресурс | Тип | Аналог в docker compose |
|---|---|---|
| `fastapi-docker-deploy` | Web Service, сборка из `Dockerfile` | `app` + `worker` |
| `fastapi-db` | PostgreSQL | `db` |
| уже существующий Key Value аккаунта | Key Value (совместим с Redis) | `redis` |

Бесплатный Key Value на аккаунте Render может быть только один. Поэтому проект подключается к уже
существующему: его Internal URL задаётся в переменной `REDIS_URL`. Чтобы не пересекаться с другим
проектом, этот пишет в отдельные базы Redis: брокер в `/2` (`CELERY_BROKER_DB`), результаты в `/3` (`CELERY_RESULT_DB`).

Переменные окружения связывают сервисы через их **внутренние адреса Render**, так же как имена сервисов в `.env.docker`:

```yaml
- key: DATABASE_URL
  fromDatabase: { name: fastapi-db, property: connectionString }
- key: REDIS_URL          # Internal URL Key Value, вводится в Dashboard
  sync: false
```

- `SECRET_KEY` Render генерирует сам (`generateValue: true`).
- `ADMIN_PASSWORD` вводится в Dashboard при создании (`sync: false`), поэтому в репозиторий не попадает.
- Публичный адрес Render передаёт в `RENDER_EXTERNAL_URL`, и приложение само добавляет его в CORS (`app/config.py`).
- Адрес БД вида `postgresql://...` приложение переводит в `postgresql+psycopg://...`.
- Render проверяет `/health` перед тем, как переключить трафик на новую версию.

Ограничения бесплатного тарифа:
- **Нет Background Worker**, поэтому Celery-воркер запускается в том же контейнере, что и API (`dockerCommand` в `render.yaml`, `--pool=solo`). Вместе они занимают около 130 МБ из 512 МБ.
- Сервис засыпает после 15 минут простоя и просыпается примерно за минуту.
- Бесплатная PostgreSQL удаляется через 30 дней после создания.

### Как развернуть

1. Войдите на https://dashboard.render.com через GitHub.
2. **New → Blueprint** и выберите репозиторий `fastapi-docker-deploy` (при первом входе дайте Render доступ к нему).
3. Render прочитает `render.yaml` и покажет ресурсы. Введите `ADMIN_PASSWORD`, а в `REDIS_URL` вставьте
   **Internal Key Value URL** со страницы своего Key Value (он должен быть в регионе Frankfurt).
   Нажмите **Deploy Blueprint**.
4. Дождитесь статуса **Live**: первая сборка идёт примерно 5 минут. Адрес вида `https://fastapi-docker-deploy.onrender.com` будет вверху страницы сервиса.
5. Проверьте `/health` и `/docs`.

Дальше каждый push в `main` запускает CI в GitHub Actions и автодеплой на Render.

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
render.yaml                деплой на Render: web + PostgreSQL (+ существующий Key Value)
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
tests/                     35 тестов
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
