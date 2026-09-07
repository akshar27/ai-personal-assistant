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

# Run migrations, then serve. PORT is honoured for hosts that inject it.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
