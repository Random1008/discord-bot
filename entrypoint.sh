#!/bin/sh
set -e

(cd shared && alembic upgrade head)

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python main.py
