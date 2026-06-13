"""참조 엔드포인트 통합 테스트. DB AsyncMock과 서비스 패치 방식을 사용한다."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("APP_ENV", "development")

from app.api.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.commodity import (  # noqa: E402
    CommodityDetail,
    CommodityListResponse,
    CommoditySummary,
    SegmentItem,
    SegmentListResponse,
    SegmentMeta,
)
from app.schemas.meta import EventItem, EventListResponse, FreshnessResponse  # noqa: E402

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reference_dummy.json"

with _FIXTURE_PATH.open(encoding="utf-8") as _f:
    _FIXTURE: dict[str, Any] = json.load(_f)


def _build_commodity_list() -> CommodityListResponse:
    items = [
        CommoditySummary(
            commodity_id=c["commodity_id"],
            name_kr=c["name_kr"],
            name_en=c["name_en"],
            cluster=c["cluster"],
            has_wholesale=c["has_wholesale"],
            route_type=c["route_type"],
            segments=c["segments"],
            analysis_start=c["analysis_start"],
            analysis_end=c["analysis_end"],
            has_anomaly_this_month=c["has_anomaly_this_month"],
            latest_anomaly_grade=c["latest_anomaly_grade"],
        )
        for c in _FIXTURE["GET /api/v1/commodities"]["commodities"]
    ]
    return CommodityListResponse(commodities=items)


def _build_commodity_detail(commodity_id: str) -> CommodityDetail:
    key = f"GET /api/v1/commodities/{commodity_id}"
    raw = _FIXTURE[key]
    seg_meta = {
        seg_id: SegmentMeta(
            model_type=m["model_type"],
            cointegrated=m["cointegrated"],
            normal_transmission_lag=m["normal_transmission_lag"],
            transmission_elasticity=m["transmission_elasticity"],
            upstream_label=m["upstream_label"],
            downstream_label=m["downstream_label"],
            warmup_end=m["warmup_end"],
        )
        for seg_id, m in raw["segment_meta"].items()
    }
    return CommodityDetail(
        commodity_id=raw["commodity_id"],
        name_kr=raw["name_kr"],
        name_en=raw["name_en"],
        cluster=raw["cluster"],
        has_wholesale=raw["has_wholesale"],
        route_type=raw["route_type"],
        segments=raw["segments"],
        analysis_start=raw["analysis_start"],
        analysis_end=raw["analysis_end"],
        has_anomaly_this_month=raw["has_anomaly_this_month"],
        latest_anomaly_grade=raw["latest_anomaly_grade"],
        segment_meta=seg_meta,
    )


def _build_segments() -> tuple[SegmentListResponse, str]:
    import hashlib

    items = [
        SegmentItem(
            segment_id=s["segment_id"],
            label_kr=s["label_kr"],
            upstream_label=s["upstream_label"],
            downstream_label=s["downstream_label"],
            applies_to=s["applies_to"],
            pattern1=s["pattern1"],
            pattern2=s["pattern2"],
            pattern3=s["pattern3"],
            ml_applied=s["ml_applied"],
        )
        for s in _FIXTURE["GET /api/v1/segments"]["segments"]
    ]
    response = SegmentListResponse(segments=items)
    body = json.dumps(response.model_dump(), ensure_ascii=False, sort_keys=True, default=str)
    etag = hashlib.sha256(body.encode()).hexdigest()[:32]
    return response, etag


def _build_events() -> tuple[EventListResponse, str]:
    import hashlib

    items = [
        EventItem(
            event_key=e["event_key"],
            label_kr=e["label_kr"],
            start_date=e["start_date"],
            end_date=e["end_date"],
            color_hex=e["color_hex"],
        )
        for e in _FIXTURE["GET /api/v1/events"]["events"]
    ]
    response = EventListResponse(events=items)
    body = json.dumps(response.model_dump(), ensure_ascii=False, sort_keys=True, default=str)
    etag = hashlib.sha256(body.encode()).hexdigest()[:32]
    return response, etag


def _build_freshness() -> FreshnessResponse:
    raw = _FIXTURE["GET /api/v1/freshness"]
    return FreshnessResponse(
        data_up_to=raw["data_up_to"],
        next_run_date=raw["next_run_date"],
        last_updated=raw["last_updated"],
    )


async def _override_get_db():
    yield AsyncMock()


@pytest.fixture(autouse=True)
def _db_override():
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# 1. GET /api/v1/commodities

@pytest.mark.asyncio
async def test_commodities_list_200():
    """GET /commodities 200 OK + 품목 10개."""
    with patch("app.services.reference.get_commodities", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_list()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities")

    assert resp.status_code == 200
    body = resp.json()
    assert "commodities" in body
    assert len(body["commodities"]) == 10


@pytest.mark.asyncio
async def test_commodities_list_fields():
    """각 품목 필수 필드 및 Literal 값 검증."""
    allowed_clusters = {"grain", "oil_sugar", "tropical", "livestock", "independent"}
    allowed_route_types = {"3seg", "4seg"}
    _yyyymm = re.compile(r"^\d{4}-\d{2}$")

    with patch("app.services.reference.get_commodities", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_list()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities")

    for c in resp.json()["commodities"]:
        assert c["cluster"] in allowed_clusters, f"cluster 범위 초과: {c['cluster']}"
        assert c["route_type"] in allowed_route_types, f"route_type 범위 초과: {c['route_type']}"
        assert isinstance(c["segments"], list) and len(c["segments"]) > 0
        assert isinstance(c["has_anomaly_this_month"], bool)
        assert c["latest_anomaly_grade"] is None   # Phase 7 전 null
        assert c["has_anomaly_this_month"] is False  # Phase 7 전 false
        for period_field in ("analysis_start", "analysis_end"):
            assert _yyyymm.match(c[period_field]), f"{period_field} YYYY-MM 형식 불일치: {c[period_field]}"


@pytest.mark.asyncio
async def test_commodities_list_snake_case():
    """응답 키가 snake_case인지 확인."""
    with patch("app.services.reference.get_commodities", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_list()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities")

    c = resp.json()["commodities"][0]
    # camelCase 키가 없어야 함
    assert "hasWholesale" not in c
    assert "routeType" not in c
    assert "hasAnomalyThisMonth" not in c
    assert "latestAnomalyGrade" not in c
    # snake_case 키 존재
    assert "has_wholesale" in c
    assert "route_type" in c
    assert "has_anomaly_this_month" in c
    assert "latest_anomaly_grade" in c


@pytest.mark.asyncio
async def test_commodities_3seg_segments():
    """route_type='3seg' 품목은 segments=['A','B','D_prime']."""
    with patch("app.services.reference.get_commodities", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_list()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities")

    for c in resp.json()["commodities"]:
        if c["route_type"] == "3seg":
            assert c["segments"] == ["A", "B", "D_prime"], f"3seg 구간 불일치: {c['segments']}"
        else:
            assert c["segments"] == ["A", "B", "C", "D"], f"4seg 구간 불일치: {c['segments']}"


# 2. GET /api/v1/commodities/{id}

@pytest.mark.asyncio
async def test_commodity_detail_wheat_200():
    """wheat 상세 조회 200 OK."""
    with patch("app.services.reference.get_commodity_detail", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_detail("wheat")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities/wheat")

    assert resp.status_code == 200
    body = resp.json()
    assert body["commodity_id"] == "wheat"
    assert body["route_type"] == "3seg"
    assert body["segments"] == ["A", "B", "D_prime"]


@pytest.mark.asyncio
async def test_commodity_detail_segment_meta_wheat():
    """wheat segment_meta. A/B/D_prime 구간 메타를 검증한다."""
    _yyyymm = re.compile(r"^\d{4}-\d{2}$")
    with patch("app.services.reference.get_commodity_detail", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_detail("wheat")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities/wheat")

    meta = resp.json()["segment_meta"]
    assert set(meta.keys()) == {"A", "B", "D_prime"}
    for seg_id, m in meta.items():
        assert m["model_type"] in ("VAR", "VECM"), f"{seg_id} model_type 범위 초과"
        assert isinstance(m["cointegrated"], bool)
        assert isinstance(m["normal_transmission_lag"], int)
        assert isinstance(m["transmission_elasticity"], float)
        assert _yyyymm.match(m["warmup_end"]), f"{seg_id} warmup_end YYYY-MM 불일치"


@pytest.mark.asyncio
async def test_commodity_detail_banana_4seg():
    """banana 상세. 4seg segments와 C/D 구간 포함 segment_meta를 검증한다."""
    with patch("app.services.reference.get_commodity_detail", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_commodity_detail("banana")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities/banana")

    assert resp.status_code == 200
    body = resp.json()
    assert body["segments"] == ["A", "B", "C", "D"]
    assert set(body["segment_meta"].keys()) == {"A", "B", "C", "D"}


@pytest.mark.asyncio
async def test_commodity_detail_not_found_404():
    """존재하지 않는 품목 조회 시 404와 COMMODITY_NOT_FOUND를 반환한다."""
    from app.core.exceptions import APIError

    def _raise(*_args, **_kwargs):
        raise APIError(
            "API-COM-001",
            "요청한 품목을 찾을 수 없습니다.",
            context={"commodity_id": "nonexistent"},
            http_status=404,
            public_code="COMMODITY_NOT_FOUND",
        )

    with patch("app.services.reference.get_commodity_detail", side_effect=_raise):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities/nonexistent")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "COMMODITY_NOT_FOUND"
    assert "context" in body["error"]
    assert body["error"]["context"]["commodity_id"] == "nonexistent"


@pytest.mark.asyncio
async def test_commodity_detail_error_envelope():
    """에러 응답 envelope 구조: {"error": {"code", "message", "context"}}."""
    from app.core.exceptions import APIError

    with patch(
        "app.services.reference.get_commodity_detail",
        side_effect=APIError(
            "API-COM-001",
            "요청한 품목을 찾을 수 없습니다.",
            context={"commodity_id": "bad"},
            http_status=404,
            public_code="COMMODITY_NOT_FOUND",
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/commodities/bad")

    body = resp.json()
    assert "error" in body, "최상위 'error' 키 없음"
    err = body["error"]
    for key in ("code", "message", "context"):
        assert key in err, f"error 내 '{key}' 키 없음"


# 3. GET /api/v1/segments

@pytest.mark.asyncio
async def test_segments_200():
    """GET /segments 200 OK + 5개 구간."""
    with patch("app.services.reference.get_segments", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_segments()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/segments")

    assert resp.status_code == 200
    body = resp.json()
    assert "segments" in body
    assert len(body["segments"]) == 5


@pytest.mark.asyncio
async def test_segments_ids():
    """구간 ID 집합. A/B/C/D/D_prime 5종이 모두 존재해야 한다."""
    with patch("app.services.reference.get_segments", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_segments()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/segments")

    ids = {s["segment_id"] for s in resp.json()["segments"]}
    assert ids == {"A", "B", "C", "D", "D_prime"}


@pytest.mark.asyncio
async def test_segments_etag_header():
    """ETag 헤더 존재 및 형식 (쌍따옴표 포함)."""
    with patch("app.services.reference.get_segments", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_segments()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/segments")

    assert "etag" in resp.headers, "ETag 헤더 없음"
    etag = resp.headers["etag"]
    assert etag.startswith('"') and etag.endswith('"'), f"ETag 쌍따옴표 형식 불일치: {etag}"


@pytest.mark.asyncio
async def test_segments_cache_control_header():
    """Cache-Control: public, max-age=86400."""
    with patch("app.services.reference.get_segments", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_segments()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/segments")

    cc = resp.headers.get("cache-control", "")
    assert "public" in cc, f"Cache-Control에 'public' 없음: {cc}"
    assert "max-age=86400" in cc, f"Cache-Control에 'max-age=86400' 없음: {cc}"


@pytest.mark.asyncio
async def test_segments_fields():
    """구간 항목 필수 필드 검증."""
    with patch("app.services.reference.get_segments", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_segments()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/segments")

    for s in resp.json()["segments"]:
        for key in ("segment_id", "label_kr", "upstream_label", "downstream_label",
                    "applies_to", "pattern1", "pattern2", "pattern3", "ml_applied"):
            assert key in s, f"'{key}' 키 없음"
        assert isinstance(s["pattern1"], bool)
        assert isinstance(s["pattern2"], bool)
        assert isinstance(s["pattern3"], bool)
        assert isinstance(s["ml_applied"], bool)


# 4. GET /api/v1/events

@pytest.mark.asyncio
async def test_events_200():
    """GET /events 200 OK + 5개 이벤트."""
    with patch("app.services.reference.get_events", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_events()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/events")

    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert len(body["events"]) == 5


@pytest.mark.asyncio
async def test_events_date_format():
    """이벤트 start_date/end_date YYYY-MM 형식."""
    _yyyymm = re.compile(r"^\d{4}-\d{2}$")
    with patch("app.services.reference.get_events", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_events()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/events")

    for e in resp.json()["events"]:
        assert _yyyymm.match(e["start_date"]), f"start_date 형식 불일치: {e['start_date']}"
        assert _yyyymm.match(e["end_date"]), f"end_date 형식 불일치: {e['end_date']}"


@pytest.mark.asyncio
async def test_events_etag_and_cache_headers():
    """ETag + Cache-Control 헤더 동시 존재."""
    with patch("app.services.reference.get_events", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_events()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/events")

    assert "etag" in resp.headers, "ETag 헤더 없음"
    cc = resp.headers.get("cache-control", "")
    assert "max-age=86400" in cc, f"Cache-Control 불일치: {cc}"


@pytest.mark.asyncio
async def test_events_etag_stable():
    """같은 데이터 2회 요청 시 ETag가 동일해야 한다. 캐시 안정성 검증."""
    with patch("app.services.reference.get_events", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_events()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r1 = await ac.get("/api/v1/events")
            mock_svc.return_value = _build_events()
            r2 = await ac.get("/api/v1/events")

    assert r1.headers["etag"] == r2.headers["etag"], "동일 데이터에 대해 ETag가 달라짐"


# 5. GET /api/v1/freshness

@pytest.mark.asyncio
async def test_freshness_200():
    """GET /freshness 200 OK."""
    with patch("app.services.reference.get_freshness", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_freshness()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/freshness")

    assert resp.status_code == 200
    body = resp.json()
    for key in ("data_up_to", "next_run_date", "last_updated"):
        assert key in body, f"'{key}' 키 없음"


@pytest.mark.asyncio
async def test_freshness_date_formats():
    """날짜 직렬화 형식 검증 (YYYY-MM / YYYY-MM-DD / ISO-8601-Z)."""
    _yyyymm = re.compile(r"^\d{4}-\d{2}$")
    _yyyymmdd = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    _iso8601z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    with patch("app.services.reference.get_freshness", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_freshness()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/freshness")

    body = resp.json()
    assert _yyyymm.match(body["data_up_to"]), f"data_up_to YYYY-MM 불일치: {body['data_up_to']}"
    assert _yyyymmdd.match(body["next_run_date"]), f"next_run_date YYYY-MM-DD 불일치: {body['next_run_date']}"
    assert _iso8601z.match(body["last_updated"]), f"last_updated ISO-8601-Z 불일치: {body['last_updated']}"


@pytest.mark.asyncio
async def test_freshness_fixture_values():
    """픽스처 기댓값과 응답 값 정확히 일치."""
    expected = _FIXTURE["GET /api/v1/freshness"]
    with patch("app.services.reference.get_freshness", new_callable=AsyncMock) as mock_svc:
        mock_svc.return_value = _build_freshness()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/freshness")

    body = resp.json()
    assert body["data_up_to"] == expected["data_up_to"]
    assert body["next_run_date"] == expected["next_run_date"]
    assert body["last_updated"] == expected["last_updated"]
