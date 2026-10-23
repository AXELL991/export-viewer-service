# ============================================================
# Etapa 1: builder - instala dependencias con uv
# ============================================================
FROM python:3.12-slim AS builder

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:0.5.5 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ============================================================
# Etapa 2: runtime - imagen mínima sin herramientas de build
# ============================================================
FROM python:3.12-slim AS runtime

# Usuario no root
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copiar virtualenv desde el builder
COPY --from=builder /app/.venv /app/.venv

# Copiar código fuente
COPY app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Healthcheck contra el propio endpoint de liveness
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

USER appuser

EXPOSE 8000

# Un solo worker por contenedor y apagado ordenado con 25 s.
# uvicorn maneja SIGTERM y finaliza las requests en vuelo.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "25"]
