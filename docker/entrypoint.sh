#!/bin/sh
set -eu

alembic upgrade head
python -m app.cli.seed_users

exec "$@"

