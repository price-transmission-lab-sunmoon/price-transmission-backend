"""Redis 클라이언트 초기화 및 ping — exception_spec_vN DB-CACHE-001 대응."""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

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
    """Redis 연결 확인. 실패 시 WARN 후 False 반환 (서비스 중단 없음, DB-CACHE-001)."""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as e:
        logger.warning(
            "Redis 연결 실패 — 캐시 없이 DB 직접 조회",
            extra={"error_code": "DB-CACHE-001", "context": {"error": str(e)}},
        )
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
