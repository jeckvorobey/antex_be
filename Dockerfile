FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Проверка использует только стандартную библиотеку Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"]

# entrypoint применяет Alembic-миграции перед запуском API.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "python", "run.py", "--no-reload", "--host", "0.0.0.0", "--port", "8000"]
