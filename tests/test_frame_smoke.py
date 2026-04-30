"""Frame 단계 smoke test 3건 — frame_spec §7.4.

DB / Redis 없이 더미 응답 기준으로 동작 검증.
APP_ENV=development 이므로 DB/Redis 미연결 시 WARN 후 기동.
"""
from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("APP_ENV", "development")

from app.main import app  # noqa: E402

# ── Test 1: 앱 기동 + /meta/config 응답 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_app_startup():
    """/meta/config 200 OK + 필수 키 4종 확인 (frame_spec §7.4 #1)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/meta/config")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("app_env", "db_status", "redis_status", "frame_version"):
        assert key in body, f"응답에 '{key}' 키 없음: {body}"


# ── Test 2: /commodities 더미 10개 검증 ──────────────────────────────────────

ALLOWED_CLUSTERS = {"grain", "oil_sugar", "tropical", "livestock", "independent"}
ALLOWED_ROUTE_TYPES = {"3seg", "4seg"}

@pytest.mark.asyncio
async def test_commodities_dummy():
    """/commodities 10개 품목 배열 + 필드·Literal 값 검증 (frame_spec §7.4 #2)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/commodities")
    assert resp.status_code == 200
    items = resp.json()["commodities"]
    assert len(items) == 10, f"품목 수 불일치: {len(items)}"
    for c in items:
        for key in ("commodity_id", "cluster", "route_type", "segments"):
            assert key in c, f"'{key}' 키 없음: {c}"
        assert c["cluster"] in ALLOWED_CLUSTERS, f"허용되지 않은 cluster: {c['cluster']}"
        assert c["route_type"] in ALLOWED_ROUTE_TYPES, f"허용되지 않은 route_type: {c['route_type']}"
        assert isinstance(c["segments"], list), "segments가 배열이 아님"


# ── Test 3: period 형식 검증 (YYYY-MM validator) ──────────────────────────────

@pytest.mark.asyncio
async def test_period_validator():
    """YYYY-MM validator — 잘못된 형식 입력 시 예외 발생 확인 (frame_spec §7.4 #3).

    Frame 단계 endpoint는 from/to query param을 받지 않는 더미 응답이므로
    TimeseriesEnvelope 스키마 validator를 직접 단위 테스트한다.
    """
    import pydantic

    from app.schemas.timeseries import TimeseriesEnvelope

    valid_base = dict(
        requested_to="2026-03",
        actual_from="2026-03",
        actual_to="2026-03",
        granularity="monthly",
        total_points=0,
    )

    # zero-pad 없는 월 (2026-3)
    with pytest.raises((pydantic.ValidationError, ValueError)):
        TimeseriesEnvelope(requested_from="2026-3", **valid_base)

    # 월초가 아닌 날짜 (2026-03-15)
    with pytest.raises((pydantic.ValidationError, ValueError)):
        TimeseriesEnvelope(requested_from="2026-03-15", **valid_base)
