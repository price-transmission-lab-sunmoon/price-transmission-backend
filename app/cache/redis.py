"""Redis 클라이언트 초기화, ping, 캐시 헬퍼."""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import redis.asyncio as aioredis
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger("app")

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def ping_redis() -> bool:
    """Redis 연결 확인 — 실패 시 경고만 출력하고 False 반환."""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as e:
        logger.warning(
            "Redis 연결 실패 — 캐시 없이 DB 직접 조회 (DB-CACHE-001)",
            extra={"error_code": "DB-CACHE-001", "context": {"error": str(e)}},
        )
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def _redacted_redis_url() -> str:
    """접속 URL에서 자격증명(user:pass@) 제거 — 로그 노출 방지."""
    url = settings.redis_url
    return url.split("@")[-1] if "@" in url else url


async def cache_get(client: aioredis.Redis, key: str) -> dict | None:
    """Redis에서 값을 읽어 dict로 반환. 연결 실패·역직렬화 오류 시 None 반환."""
    try:
        raw: str | None = await client.get(key)
    except Exception as e:
        redis_url_redacted = _redacted_redis_url()
        logger.warning(
            "Redis 연결 실패 — 캐시 없이 DB 직접 조회 (DB-CACHE-001)",
            extra={
                "error_code": "DB-CACHE-001",
                "context": {
                    "redis_url_redacted": redis_url_redacted,
                    "error_type": type(e).__name__,
                },
            },
        )
        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Redis 캐시 JSON 역직렬화 실패 — 해당 키 삭제 후 DB 재조회 (DB-CACHE-002)",
            extra={
                "error_code": "DB-CACHE-002",
                "context": {
                    "cache_key": key,
                    "raw_value_preview": raw[:200] if raw else "",
                },
            },
        )
        try:
            await client.delete(key)
        except Exception:
            pass
        return None


async def cache_set(client: aioredis.Redis, key: str, value: dict, ttl: int) -> None:
    """Redis에 dict를 JSON 직렬화하여 TTL과 함께 저장 — 연결 실패 시 무시."""
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:
        redis_url_redacted = _redacted_redis_url()
        logger.warning(
            "Redis 캐시 쓰기 실패 — 캐시 저장 생략 (DB-CACHE-001)",
            extra={
                "error_code": "DB-CACHE-001",
                "context": {
                    "redis_url_redacted": redis_url_redacted,
                    "error_type": type(e).__name__,
                    "cache_key": key,
                },
            },
        )


async def cache_delete(client: aioredis.Redis, key: str) -> None:
    """단일 캐시 키 삭제. 연결 실패는 무시한다."""
    try:
        await client.delete(key)
    except Exception:
        pass


async def cache_delete_pattern(client: aioredis.Redis, pattern: str) -> int:
    """SCAN으로 패턴 매칭 키를 모두 삭제하고 삭제 건수를 반환."""
    try:
        keys: list[str] = []
        async for key in client.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            await client.delete(*keys)
        return len(keys)
    except Exception as e:
        redis_url_redacted = _redacted_redis_url()
        logger.warning(
            "Redis 패턴 캐시 삭제 실패 (DB-CACHE-001)",
            extra={
                "error_code": "DB-CACHE-001",
                "context": {
                    "redis_url_redacted": redis_url_redacted,
                    "error_type": type(e).__name__,
                    "pattern": pattern,
                },
            },
        )
        return 0


T = TypeVar("T", bound=BaseModel)

# TODO: TTL을 엔드포인트별로 분리 적용하는 방안 검토

async def cached_or_compute(
    client: aioredis.Redis,
    cache_key: str,
    model_cls: type[T],
    compute: Callable[[], Awaitable[T]],
    *,
    ttl: int | None = None,
) -> T:
    """캐시 HIT 시 Pydantic 검증 후 반환, MISS 시 compute() 실행 후 적재.

    HIT 값 검증 실패 시 캐시 무효화 후 compute() 폴백.
    """
    cached = await cache_get(client, cache_key)
    if cached is not None:
        try:
            result = model_cls.model_validate(cached)
            logger.info(
                "cache=hit",
                extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
            )
            return result
        except ValidationError as e:
            logger.warning(
                "Redis 캐시값 Pydantic 검증 실패 — 캐시 무효화 후 DB 재조회 (PARSE-REDIS-001)",
                extra={
                    "error_code": "PARSE-REDIS-001",
                    "context": {"cache_key": cache_key, "error_msg": str(e)},
                },
            )
            await cache_delete(client, cache_key)

    logger.info(
        "cache=miss",
        extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
    )
    result = await compute()
    await cache_set(
        client, cache_key, result.model_dump(mode="json"),
        ttl=ttl if ttl is not None else settings.redis_ttl,
    )
    return result
