# ==========================================
# Stage 1: Builder - Install dependencies
# ==========================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

# Copy only dependency files to leverage Docker cache
COPY pyproject.toml uv.lock ./

# Export requirements and install to a custom prefix
# This creates a clean, portable Python environment
#
# --no-default-groups, not --no-dev. pyproject.toml sets
# default-groups = ["dev", "test"] so a fresh clone can run the suite without
# extra flags, and --no-dev is an alias for --no-group dev: it would drop `dev`
# and let `test` through, shipping pytest, coverage, testcontainers and the
# docker client into this image. Keep the two in step -- see the comment beside
# default-groups in pyproject.toml.
RUN uv export --frozen --no-default-groups --format requirements-txt -o requirements.txt && \
    uv pip install --no-cache-dir --python /usr/local/bin/python --prefix=/install -r requirements.txt && \
    # Remove unnecessary files to reduce size
    find /install -type d -name "tests" -o -name "test" -o -name "__pycache__" | xargs rm -rf && \
    find /install -type f -name "*.pyc" -o -name "*.pyo" | xargs rm -rf && \
    # Strip debug symbols from shared libraries
    find /install -name "*.so" -exec strip --strip-unneeded {} \; 2>/dev/null || true

# ==========================================
# Stage 2: Runtime - Minimal final image
# ==========================================
FROM python:3.13-slim AS runtime

ARG APP_ENV=production

ENV APP_ENV=${APP_ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONPATH=/app

# Install only runtime dependencies (libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    libgfortran5 \
    libopenblas0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Remove pip, setuptools, and wheel from runtime to save space (~7 MB)
# These are not needed in production as all dependencies are already installed
RUN pip uninstall -y pip setuptools wheel || true

# Create non-root user before copying files
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy only necessary application files
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./
# Not just a build input: app/core/metadata.py reads the service's title,
# version, description and API prefix out of [tool.app.metadata] at import time,
# so the file has to exist at runtime or the app cannot start. It resolves as
# ../../pyproject.toml from app/core/, which is /app/pyproject.toml here.
COPY --chown=appuser:appuser pyproject.toml ./
# Copy the whole scripts/ dir rather than naming one file: .dockerignore
# denylists the host-only scripts (build-docker.sh, run-docker.sh, …), so only
# container scripts land here, and a newly added one can't be silently omitted
# from the image. Keep that denylist accurate when adding host-only scripts.
COPY --chown=appuser:appuser scripts/ ./scripts/

# Make container scripts executable
RUN chmod +x /app/scripts/*.sh

# app.core.config creates ./logs at import time (LoggingSettings.ensure_path).
# /app is root-owned, so appuser cannot create it — any container without a
# logs bind mount would die with PermissionError before reaching its command.
RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

# Switch to non-root user
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"] 