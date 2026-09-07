# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd -m app && mkdir -p /app/storage && chown -R app:app /app
USER app

EXPOSE 8000

# Migrations run out-of-band: `[deploy].release_command` on Fly, an explicit
# command in docker-compose. This entrypoint just serves. $PORT is honoured.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
