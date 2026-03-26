#!/usr/bin/env sh
set -e

uv run alembic upgrade head

exec "$@"
