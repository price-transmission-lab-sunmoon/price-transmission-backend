#!/bin/sh
# DB 스냅샷 생성 (Mac/Linux) — 적재 완료된 pt_postgres → db/snapshot.sql.gz
#
# 사전: docker start pt_postgres
# 사용: sh scripts/make-snapshot.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/db/snapshot.sql.gz"
mkdir -p "$ROOT/db"

echo "[snapshot] pg_dump + gzip -> $OUT"
docker exec pt_postgres sh -c "pg_dump -U postgres -d price_transmission --no-owner --no-privileges | gzip -c" > "$OUT"

if [ ! -s "$OUT" ]; then
  echo "[snapshot] 실패: 스냅샷이 비어 있음 — pt_postgres 기동 상태 확인" >&2
  exit 1
fi
echo "[snapshot] 완료: $OUT ($(wc -c < "$OUT") bytes)"
