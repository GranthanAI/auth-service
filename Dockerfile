# ==============================================================================
# STAGE 1: Builder
# ==============================================================================
FROM python:3.12-slim AS builder

# Set build-time environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

# Install uv package installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build

# Copy dependency files first to leverage layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ==============================================================================
# STAGE 2: Runtime
# ==============================================================================
FROM python:3.12-slim AS runtime

# Set runtime environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create a non-privileged system user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -s /sbin/nologin appuser

WORKDIR /app

# Copy only the compiled virtual environment from the builder stage
COPY --from=builder /build/.venv /app/.venv

# Copy the service source code and schemas
COPY app /app/app
COPY init_db.py /app/
COPY README.md /app/

# Set correct ownership for the runtime user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose FastAPI application port
EXPOSE 8000

# Run FastAPI app using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
