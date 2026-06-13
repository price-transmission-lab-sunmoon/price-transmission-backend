"""FastAPI 진입점. lifespan, CORS, 전역 예외 핸들러, 라우터 등록."""
from __future__ import annotations

import io
import logging
import sys
from contextlib import asynccontextmanager

# Windows cp949 환경에서 UTF-8 출력 강제
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.cache.redis import close_redis, ping_redis
from app.core.config import settings
from app.core.exceptions import (
    APIError,
    ConfigError,
    api_error_handler,
    internal_error_handler,
    validation_error_handler,
)
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """부팅 시 DB/Redis 연결 확인 후 스케줄러 기동.

    development 환경에서는 연결 실패 시 경고만 출력하고 계속 기동한다.
    """
    setup_logging(settings.log_level)
    logger = logging.getLogger("app")
    logger.info("서버 시작", extra={"error_code": "BOOT", "context": {"app_env": settings.app_env}})

    import sqlalchemy

    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        logger.info("PostgreSQL 연결 확인", extra={"error_code": "BOOT", "context": {}})
    except Exception as e:
        if settings.app_env == "development":
            logger.warning(
                "PostgreSQL 연결 실패. development 모드이므로 기동 계속",
                extra={"error_code": "CFG-CORE-001", "context": {"error": str(e)}},
            )
        else:
            logger.critical(
                "PostgreSQL 연결 실패. 서버 기동 중단",
                extra={"error_code": "CFG-CORE-001", "context": {"error": str(e)}},
            )
            raise ConfigError(
                "CFG-CORE-001",
                "PostgreSQL 연결 실패",
                {"error": str(e)},
            ) from e

    redis_ok = await ping_redis()
    if not redis_ok and settings.app_env != "development":
        logger.critical(
            "Redis 연결 실패. 서버 기동 중단",
            extra={"error_code": "CFG-CORE-001", "context": {}},
        )
        raise ConfigError("CFG-CORE-001", "Redis 연결 실패")

    from app.services.batch import init_scheduler

    _scheduler = init_scheduler()
    _scheduler.start()
    logger.info(
        "APScheduler 시작. 월별 배치 스케줄 등록",
        extra={"error_code": "BOOT", "context": {}},
    )

    yield

    _scheduler.shutdown(wait=False)
    logger.info("APScheduler 종료", extra={"error_code": "BOOT", "context": {}})

    await close_redis()
    await engine.dispose()
    logger.info("서버 종료", extra={"error_code": "BOOT", "context": {}})


app = FastAPI(
    title="price-transmission-backend",
    version=settings.frame_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, internal_error_handler)

app.include_router(router)
