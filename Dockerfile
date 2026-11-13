FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# The application applies this idempotent schema on startup; PostgreSQL also
# reads the Compose-mounted copy when it initializes a brand-new data directory.
COPY database ./database

# The demo image also carries the test tooling so tests can run inside Compose
# on hosts that must not install Python packages (the G7 server).
RUN python -m pip install ".[dev]"

COPY tests ./tests

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# One image, one package, two processes: compose selects the console script.
CMD ["crm-api"]
