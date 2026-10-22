#!/usr/bin/env sh
set -e

echo "[*] Starting Acme Hospital Clinic Booking Application..."

# Wait for PostgreSQL to become reachable
echo "[*] Checking PostgreSQL database connectivity..."
python - << 'EOF'
import sys
import time
from sqlalchemy import create_engine, text
from app.core.config import settings

max_retries = 30
retry_interval = 2

for attempt in range(1, max_retries + 1):
    try:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[+] Database connection established (attempt {attempt}).")
        sys.exit(0)
    except Exception as e:
        print(f"[-] Database not ready yet (attempt {attempt}/{max_retries}): {e}")
        time.sleep(retry_interval)

print("[!] Could not connect to PostgreSQL within timeout period.", file=sys.stderr)
sys.exit(1)
EOF

# Run database migrations
echo "[*] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

# Seed initial clinic baseline data (strictly idempotent)
echo "[*] Seeding clinic baseline data (python seed.py)..."
python seed.py

# Start Uvicorn application server
echo "[*] Launching Uvicorn server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
