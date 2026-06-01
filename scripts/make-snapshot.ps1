# DB 스냅샷 생성 (Windows) — 적재 완료된 pt_postgres → db/snapshot.sql.gz
#
# 사전: docker start pt_postgres  (적재가 끝난 로컬 개발 DB)
# 사용: powershell -ExecutionPolicy Bypass -File scripts\make-snapshot.ps1
#
# gzip은 컨테이너 내부에서 처리하고 docker cp로 꺼낸다
# (PowerShell '>' 리다이렉트는 바이너리를 UTF-16으로 깨뜨리므로 사용하지 않음).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dbDir = Join-Path $root "db"
$out = Join-Path $dbDir "snapshot.sql.gz"
New-Item -ItemType Directory -Force $dbDir | Out-Null

Write-Host "[snapshot] pg_dump + gzip (컨테이너 내부)"
docker exec pt_postgres sh -c "pg_dump -U postgres -d price_transmission --no-owner --no-privileges | gzip -c > /tmp/snapshot.sql.gz"
if ($LASTEXITCODE -ne 0) { throw "pg_dump 실패 — pt_postgres 기동 상태 확인" }

Write-Host "[snapshot] docker cp -> $out"
docker cp pt_postgres:/tmp/snapshot.sql.gz $out
docker exec pt_postgres rm -f /tmp/snapshot.sql.gz

$size = (Get-Item $out).Length
if ($size -le 0) { throw "스냅샷이 0바이트" }
Write-Host ("[snapshot] 완료: {0} ({1:N0} bytes)" -f $out, $size)
