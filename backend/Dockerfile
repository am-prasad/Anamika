# syntax=docker/dockerfile:1.7
# Anamika backend image: one image, two roles (API via uvicorn, worker via arq).
# Build from the repository root:  docker build -f backend/Dockerfile -t anamika-backend .

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ---------------------------------------------------------------- build: resolve deps with uv
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv/anamika/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra api --no-install-project

# ---------------------------------------------------------------- runtime: minimal, non-root
FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="anamika-backend" \
      org.opencontainers.image.description="Anamika privacy firewall: FastAPI service + pipeline worker"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    ANAMIKA_DATA_DIR=/data \
    ANAMIKA_PIPELINE_PYTHON=/opt/venv/bin/python
RUN groupadd --system --gid 10001 anamika \
 && useradd --system --uid 10001 --gid anamika --no-create-home --shell /usr/sbin/nologin anamika \
 && mkdir -p /data && chown anamika:anamika /data && chmod 0700 /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv/anamika/backend
COPY config /srv/anamika/config
COPY backend/main.py ./
COPY backend/anamika ./anamika
COPY backend/app ./app
COPY backend/tools ./tools
USER anamika:anamika
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", \
     "--proxy-headers", "--no-server-header", "--timeout-graceful-shutdown", "20"]
