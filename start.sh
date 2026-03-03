#!/usr/bin/env bash
set -e

# Render จะส่ง PORT มาให้
PORT=${PORT:-8000}

# รัน uvicorn
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT