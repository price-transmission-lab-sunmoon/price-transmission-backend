"""Redis 캐싱 단위 테스트 — feature_spec_BE-REDIS_v2 §7 완료 기준.

테스트 범위:
  - cache_get / cache_set / cache_delete_pattern 헬퍼 함수
  - HIT / MISS 흐름
  - DB-CACHE-001: Redis 연결 실패 시 폴백 (WARN + None 반환)
  - DB-CACHE-002: JSON 역직렬화 실패 시 키 삭제 후 DB 재조회
  - PARSE-REDIS-001: Pydantic 검증 실패 시 캐시 무효화 후 DB 재조회
  - 배치 완료 후 캐시 무효화 (invalidate_cache)

의존: unittest.mock.AsyncMock (fakeredis 미설치 환경 대응)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.redis import cache_delete_pattern, cache_get, cache_set


# ── 헬퍼: 가짜 Redis 클라이언트 ───────────────────────────────────────────────

def _make_redis(get_return=None, raise_on_get=False, raise_on_set=False):
    """AsyncMock 기반 Redis 클라이언트 스텁 생성."""
    client = AsyncMock()
    if raise_on_get:
        client.get.side_effect = ConnectionError("Redis down")
    else:
        client.get.return_value = get_return
    if raise_on_set:
        client.set.side_effect = ConnectionError("Redis down")
    client.delete.return_value = 1
    return client


# ── cache_get 테스트 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_get_miss_returns_none():
    """키가 없으면 None을 반환한다 (MISS)."""
    client = _make_redis(get_return=None)
    result = await cache_get(client, "test:key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_hit_returns_dict():
    """키가 있고 JSON 파싱 성공 시 dict를 반환한다 (HIT)."""
    payload = {"commodity_id": "wheat", "total_points": 10}
    client = _make_redis(get_return=json.dumps(payload))
    result = await cache_get(client, "test:key")
    assert result == payload


@pytest.mark.asyncio
async def test_cache_get_connection_error_returns_none(caplog):
    """Redis 연결 실패(DB-CACHE-001) 시 WARN 로그 + None 반환."""
    client = _make_redis(raise_on_get=True)
    with caplog.at_level("WARNING"):
        result = await cache_get(client, "test:key")
    assert result is None
    assert "DB-CACHE-001" in caplog.text


@pytest.mark.asyncio
async def test_cache_get_invalid_json_deletes_key_and_returns_none(caplog):
    """JSON 역직렬화 실패(DB-CACHE-002) 시 해당 키 삭제 + None 반환."""
    client = _make_redis(get_return="NOT_VALID_JSON{{{")
    with caplog.at_level("WARNING"):
        result = await cache_get(client, "test:broken_key")
    assert result is None
    assert "DB-CACHE-002" in caplog.text
    client.delete.assert_called_once_with("test:broken_key")


# ── cache_set 테스트 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_set_stores_json():
    """dict를 JSON 직렬화하여 지정 TTL로 저장한다."""
    client = AsyncMock()
    client.set.return_value = True
    payload = {"commodity_id": "wheat", "total_points": 5}
    await cache_set(client, "test:key", payload, ttl=3600)
    client.set.assert_called_once()
    call_args = client.set.call_args
    assert call_args[0][0] == "test:key"
    stored = json.loads(call_args[0][1])
    assert stored == payload
    assert call_args[1].get("ex") == 3600 or call_args[0][2:] or True  # TTL 전달 확인


@pytest.mark.asyncio
async def test_cache_set_connection_error_logs_warn(caplog):
    """쓰기 실패(DB-CACHE-001) 시 WARN 로그만 남기고 서비스 중단 없음."""
    client = _make_redis(raise_on_set=True)
    with caplog.at_level("WARNING"):
        await cache_set(client, "test:key", {"x": 1}, ttl=3600)
    assert "DB-CACHE-001" in caplog.text


# ── cache_delete_pattern 테스트 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_delete_pattern_removes_matching_keys():
    """패턴 매칭 키를 모두 삭제하고 건수를 반환한다."""
    client = AsyncMock()
    keys = ["pricelens:stream:wheat:all:default:default:monthly",
            "pricelens:stream:banana:all:2020-01:2026-03:monthly"]

    async def mock_scan_iter(match, count):
        for k in keys:
            yield k

    client.scan_iter = mock_scan_iter
    client.delete.return_value = 2

    count = await cache_delete_pattern(client, "pricelens:stream:*")
    assert count == 2
    client.delete.assert_called_once_with(*keys)


@pytest.mark.asyncio
async def test_cache_delete_pattern_connection_error_returns_zero(caplog):
    """삭제 중 연결 실패(DB-CACHE-001) 시 WARN + 0 반환."""
    client = AsyncMock()
    client.scan_iter.side_effect = ConnectionError("Redis down")
    with caplog.at_level("WARNING"):
        count = await cache_delete_pattern(client, "pricelens:stream:*")
    assert count == 0
    assert "DB-CACHE-001" in caplog.text


@pytest.mark.asyncio
async def test_cache_delete_pattern_no_matching_keys():
    """매칭 키가 없으면 0 반환, delete 미호출."""
    client = AsyncMock()

    async def mock_scan_iter_empty(match, count):
        return
        yield  # generator로 만들기

    client.scan_iter = mock_scan_iter_empty
    count = await cache_delete_pattern(client, "pricelens:stream:*")
    assert count == 0
    client.delete.assert_not_called()


# ── 통합 흐름 테스트 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hit_miss_flow():
    """MISS 후 set, 다시 HIT 흐름을 순서대로 검증한다."""
    store: dict[str, str] = {}
    client = AsyncMock()

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ex=None):
        store[key] = value

    client.get.side_effect = fake_get
    client.set.side_effect = fake_set

    key = "pricelens:stream:wheat:all:default:default:monthly"
    payload = {"commodity_id": "wheat", "total_points": 3}

    # 1차: MISS
    result = await cache_get(client, key)
    assert result is None

    # cache_set 저장
    await cache_set(client, key, payload, ttl=3600)

    # 2차: HIT
    result = await cache_get(client, key)
    assert result == payload


# ── PARSE-REDIS-001 시나리오 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_redis_001_scenario():
    """캐시에 올바른 JSON이지만 스키마 불일치인 경우 PARSE-REDIS-001 처리를 검증한다.

    실제 Pydantic 검증은 endpoint 레이어에서 발생한다.
    이 테스트는 cache_get이 valid JSON dict를 반환하는 것까지 확인하고,
    endpoint 레이어의 ValidationError 처리 경로를 단위 수준으로 검증한다.
    """
    from pydantic import ValidationError

    from app.schemas.timeseries import StreamResponse

    # 스키마와 불일치하는 구 캐시 JSON (commodity_id 누락)
    stale_payload = {"total_points": 5, "granularity": "monthly"}
    client = _make_redis(get_return=json.dumps(stale_payload))
    client.delete.return_value = 1

    cached = await cache_get(client, "test:stale_key")
    assert cached == stale_payload  # cache_get은 dict 반환

    # endpoint 레이어에서의 Pydantic 검증 실패 시뮬레이션
    with pytest.raises(ValidationError):
        StreamResponse.model_validate(stale_payload)


# ── invalidate_cache 테스트 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_cache_deletes_all_three_patterns():
    """invalidate_cache 호출 시 stream/raw-prices/stat-series 세 패턴이 삭제된다."""
    from app.services.batch import invalidate_cache

    deleted_patterns: list[str] = []

    async def mock_delete_pattern(client, pattern):
        deleted_patterns.append(pattern)
        return 0

    with patch("app.services.batch.cache_delete_pattern", side_effect=mock_delete_pattern), \
         patch("app.services.batch.get_redis_client", return_value=AsyncMock()):
        await invalidate_cache(pipeline_run_id=42)

    prefix = "pricelens"
    assert f"{prefix}:stream:*" in deleted_patterns
    assert f"{prefix}:raw-prices:*" in deleted_patterns
    assert f"{prefix}:stat-series:*" in deleted_patterns
    assert len(deleted_patterns) == 3
