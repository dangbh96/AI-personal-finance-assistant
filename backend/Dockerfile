# Backend FastAPI — Phase 18. Build từ thư mục gốc repo: `docker compose up -d --build`.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Cài dependency trước (đọc từ pyproject) để cache layer khi chỉ sửa code.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY knowledge ./knowledge
COPY app ./app

RUN useradd --create-home --uid 1000 pfa && mkdir -p /app/uploads && chown -R pfa /app
USER pfa

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=4).status == 200 else 1)"

# Migration trước rồi mới chạy API (idempotent: đã ở head thì không làm gì).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
