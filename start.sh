#!/bin/sh
# Starts the live website (used by the Dockerfile).
set -e
python seed.py    # fresh demo data every time the website starts
exec gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads ${GUNICORN_THREADS:-8} --timeout 180 --access-logfile -
