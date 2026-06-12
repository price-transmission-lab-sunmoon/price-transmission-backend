"""Redis 캐싱 단위 테스트 — cache_get/set/delete + HIT/MISS 흐름 + 에러 폴백."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.cache.redis import (
    cache_delete_pattern,
    cache_get,
    cache_set,
    cached_or_compute,
)


def _make_redis(get_return=None, raise_on_get=False, raise_on_set=False):
    client = AsyncMock()
    if raise_on_get:
        client.get.side_effect = ConnectionError("Redis down")
    else:
        client.get.return_value = get_return
    if raise_on_set:
        client.set.side_effect = ConnectionError("Redis down")
    client.delete.return_value = 1
    return client


@pytest.mark.asyncio
async def test_cache_get_miss_returns_none():
    """키가 없으면 None 반환 (MISS)."""
    client = _make_redis(get_return=None)
    result = await cache_get(client, "test:key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_hit_returns_dict():
    """키가 있고 JSON 파싱 성공 시 dict 반환 (HIT)."""
    payload = {"commodity_id": "wheat", "total_points": 10}
    client = _make_redis(get_return=json.dumps(payload))
    result = await cache_get(client, "test:key")
    assert result == payload


@pytest.mark.asyncio
async def test_cache_get_connection_error_returns_none(caplog):
    """Redis 연결 실패(DB-CACHE-001) → WARN 로그 + None 반환."""
    client = _make_redis(raise_on_get=True)
    with caplog.at_level("WARNING"):
        result = await cache_get(client, "test:key")
    assert result is None
    assert "DB-CACHE-001" in caplog.text


@pytest.mark.asyncio
async def test_cache_get_invalid_json_deletes_key_and_returns_none(caplog):
    """JSON 역직렬화 실패(DB-CACHE-002) → 해당 키 삭제 + None 반환."""
    client = _make_redis(get_return="NOT_VALID_JSON{{{")
    with caplog.at_level("WARNING"):
        result = await cache_get(client, "test:broken_key")
    assert result is None
    assert "DB-CACHE-002" in caplog.text
    client.delete.assert_called_once_with("test:broken_key")


@pytest.mark.asyncio
async def test_cache_set_stores_json():
    """dict를 JSON 직렬화하여 지정 TTL로 저장."""
    client = AsyncMock()
    client.set.return_value = True
    payload = {"commodity_id": "wheat", "total_points": 5}
    await cache_set(client, "test:key", payload, ttl=3600)
    client.set.assert_called_once()
    call_args = client.set.call_args
    assert call_args[0][0] == "test:key"
    stored = json.loads(call_args[0][1])
    assert stored == payload
    assert call_args[1].get("ex") == 3600


@pytest.mark.asyncio
async def test_cache_set_connection_error_logs_warn(caplog):
    """쓰기 실패(DB-CACHE-001) → WARN 로그만, 서비스 중단 없음."""
    client = _make_redis(raise_on_set=True)
    with caplog.at_level("WARNING"):
        await cache_set(client, "test:key", {"x": 1}, ttl=3600)
    assert "DB-CACHE-001" in caplog.text


@pytest.mark.asyncio
async def test_cache_delete_pattern_removes_matching_keys():
    """패턴 매칭 키를 모두 삭제하고 건수를 반환."""
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
    """삭제 중 연결 실패(DB-CACHE-001) → WARN + 0 반환."""
    client = AsyncMock()

    async def mock_scan_iter_raise(match, count):
        raise ConnectionError("Redis down")
        yield  # noqa: unreachable — async generator 마커

    client.scan_iter = mock_scan_iter_raise
    with caplog.at_level("WARNING"):
        count = await cache_delete_pattern(client, "pricelens:stream:*")
    assert count == 0
    assert "DB-CACHE-001" in caplog.text


# TODO: TTL 경계 케이스(0, 음수, 매우 큰 값) 처리 동작 검증 추가 검토
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


@pytest.mark.asyncio
async def test_hit_miss_flow():
    """MISS 후 set, 다시 HIT 흐름 순서대로 검증."""
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


@pytest.mark.asyncio
async def test_parse_redis_001_scenario():
    """올바른 JSON이지만 스키마 불일치 — PARSE-REDIS-001 경로 검증."""
    from pydantic import ValidationError

    from app.schemas.timeseries import StreamResponse

    stale_payload = {"total_points": 5, "granularity": "monthly"}  # commodity_id 누락
    client = _make_redis(get_return=json.dumps(stale_payload))
    client.delete.return_value = 1

    cached = await cache_get(client, "test:stale_key")
    assert cached == stale_payload  # cache_get은 dict 반환

    # endpoint 레이어에서의 Pydantic 검증 실패 시뮬레이션
    with pytest.raises(ValidationError):
        StreamResponse.model_validate(stale_payload)


@pytest.mark.asyncio
async def test_invalidate_cache_deletes_all_three_patterns():
    """invalidate_cache 호출 시 stream/raw-prices/stat-series 세 패턴 삭제."""
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


class _Toy(BaseModel):
    x: int


@pytest.mark.asyncio
async def test_cached_or_compute_miss_calls_compute_and_sets():
    """MISS → compute() 실행 + 결과 캐시 적재."""
    store: dict[str, str] = {}
    client = AsyncMock()

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ex=None):
        store[key] = value

    client.get.side_effect = fake_get
    client.set.side_effect = fake_set

    calls: list[int] = []

    async def compute():
        calls.append(1)
        return _Toy(x=7)

    result = await cached_or_compute(client, "k", _Toy, compute)
    assert result.x == 7
    assert calls == [1]       # compute 1회 실행
    assert "k" in store       # 캐시 적재됨


@pytest.mark.asyncio
async def test_cached_or_compute_hit_skips_compute():
    """HIT 검증 통과 → compute() 미실행."""
    client = _make_redis(get_return=json.dumps({"x": 5}))

    calls: list[int] = []

    async def compute():
        calls.append(1)
        return _Toy(x=0)

    result = await cached_or_compute(client, "k", _Toy, compute)
    assert result.x == 5
    assert calls == []        # compute 미실행


@pytest.mark.asyncio
async def test_cached_or_compute_invalid_cache_falls_back(caplog):
    """스키마 불일치(PARSE-REDIS-001) → 캐시 삭제 + compute 폴백."""
    client = _make_redis(get_return=json.dumps({"y": "bad"}))  # x 누락
    client.delete.return_value = 1

    calls: list[int] = []

    async def compute():
        calls.append(1)
        return _Toy(x=9)

    with caplog.at_level("WARNING"):
        result = await cached_or_compute(client, "k", _Toy, compute)
    assert result.x == 9
    assert calls == [1]
    assert "PARSE-REDIS-001" in caplog.text
    client.delete.assert_called_once_with("k")
