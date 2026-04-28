"""의존성 주입 — DB 세션 및 Redis 클라이언트."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
import redis.asyncio as aioredis
from app.cache.redis import get_redis_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    return get_redis_client()
