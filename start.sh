#!/bin/sh
# Starts the live website (used by the Dockerfile).
set -e
if [ -n "$DATABASE_URL" ]; then
  python seed.py --if-empty   # PostgreSQL keeps its data between restarts: only fill it the first time
else
  python seed.py              # SQLite is wiped on every restart anyway: fresh demo data every time
fi
exec gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads ${GUNICORN_THREADS:-8} --timeout 180 --access-logfile -
