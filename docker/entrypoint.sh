#!/bin/sh
# 컨테이너 진입점 — DB는 compose의 depends_on(service_healthy)로 이미 준비됨.
# alembic upgrade head는 스냅샷이 코드보다 구버전일 때만 동작하는 안전망(보통 no-op).
set -e

echo "[entrypoint] alembic upgrade head (idempotent safety net)"
alembic upgrade head || echo "[entrypoint] alembic upgrade skipped (snapshot already current or DB pending)"

echo "[entrypoint] starting uvicorn on :8001 (workers=1)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1
