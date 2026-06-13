# TeamFlow backend — production-ready image
# Base: python:3.12-slim (pinned to 3.12 per project docs; 3.13 has pwdlib regression risk)
FROM python:3.12-slim

# Install uv — the fast Python package manager
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency manifests first for layer caching:
# uv.lock + pyproject.toml — only reinstall when deps change
COPY pyproject.toml uv.lock ./

# Install all dependencies (including dev extras for the dev image).
# In production override with --no-extra dev or a separate prod stage.
RUN uv sync --extra dev --frozen --no-cache

# Copy application code
COPY . .

# Expose the application port
EXPOSE 8000

# Default command — hot-reload disabled in production; Compose overrides for dev
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
