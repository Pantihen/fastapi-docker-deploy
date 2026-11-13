#!/bin/sh
# API и Celery-воркер в одном контейнере.
# Нужен на хостингах, где отдельный сервис для воркера платный или не нужен (Railway, Render free).
# Локально в docker compose воркер — отдельный сервис, этот скрипт там не используется.
set -e

# --pool=solo — один процесс, минимум памяти
celery -A app.celery_app worker --loglevel=info --pool=solo &

# exec — uvicorn становится главным процессом и получает сигналы остановки от платформы
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
