# =============================================================================
# AIVIS.ONE Backend -- Dockerfile
# =============================================================================
#
# MULTI-STAGE BUILD:
#   Stage 1 ("builder"): installs ALL dependencies (prod + dev) into a venv.
#   Stage 2 ("runtime"): copies venv + app code + tests + scripts.
#
# Dev dependencies (pytest, ruff, mypy, httpx) are ALWAYS installed because
# tests run inside this container on the VPS. There is no separate
# "production" image -- the VPS IS the only environment.
#
# PYTHONPATH=/app ensures `from app.core.config import settings` works
# everywhere: uvicorn, alembic, pytest -- without `pip install -e .`.
#
# Sprint 9.2: pycairo (via xhtml2pdf -> svglib -> rlpycairo) requires
# C compiler + cairo headers at build time, and libcairo2 at runtime.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder -- install all dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Build deps for pycairo (C compiler, cairo headers, pkg-config).
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        gcc \
        pkg-config \
        libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir ".[dev]"

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime dep for pycairo (shared library only, no headers).
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libcairo2 && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for security.
RUN groupadd --gid 1000 aivis && \
    useradd --uid 1000 --gid aivis --shell /bin/sh aivis

COPY --from=builder /opt/venv /opt/venv

# Copy everything the app needs.
COPY app/ ./app/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY pyproject.toml ./
COPY alembic.ini ./
COPY migrations/ ./migrations/

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# CRITICAL: alembic, pytest, and CLI tools must find the `app` package.
ENV PYTHONPATH="/app"

USER aivis
EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers"]
