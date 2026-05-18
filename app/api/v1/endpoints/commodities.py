"""/commodities, /commodities/{id}, /stream, /stream/minimap,
/scatter, /raw-prices, /raw-prices/minimap 엔드포인트 (api_spec_vN §참조·시각화 엔드포인트).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.cache.redis import cache_delete, cache_get, cache_set
from app.core.config import settings
from app.core.exceptions import APIError
from app.schemas.commodity import CommodityDetail, CommodityListResponse
from app.schemas.timeseries import (
    RawPricesMinimapResponse,
    RawPricesResponse,
    ScatterResponse,
    StreamMinimapResponse,
    StreamResponse,
)
from app.services import reference as ref_svc
from app.services import raw_prices as rp_svc
from app.services import scatter as scatter_svc
from app.services import stream as stream_svc

import redis.asyncio as aioredis

logger = logging.getLogger("app")
router = APIRouter()


def _analysis_dates(commodity: CommodityDetail, commodity_id: str) -> tuple[date, date]:
    """CommodityDetail YYYY-MM 문자열 → date 변환. None이면 API-COM-002."""
    if not commodity.analysis_start or not commodity.analysis_end:
        raise APIError(
            "API-COM-002",
            "파이프라인 데이터가 미적재 상태입니다.",
            context={"commodity_id": commodity_id, "missing_field": "analysis_start/end"},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )
    y1, m1 = (int(x) for x in commodity.analysis_start.split("-"))
    y2, m2 = (int(x) for x in commodity.analysis_end.split("-"))
    return date(y1, m1, 1), date(y2, m2, 1)


# ── 참조 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("/commodities", response_model=CommodityListResponse)
async def list_commodities(
    db: AsyncSession = Depends(get_db),
) -> CommodityListResponse:
    """품목 목록 — commodities 테이블 실 DB 조회 (feature_spec_API-REF_v4 §1.2)."""
    return await ref_svc.get_commodities(db)


@router.get("/commodities/{commodity_id}", response_model=CommodityDetail)
async def get_commodity(
    commodity_id: str,
    db: AsyncSession = Depends(get_db),
) -> CommodityDetail:
    """단일 품목 상세 + segment_meta — baselines/cointegration_results 실 DB 조회."""
    return await ref_svc.get_commodity_detail(db, commodity_id)


# ── 시각화 엔드포인트 ─────────────────────────────────────────────────────────

@router.get("/commodities/{commodity_id}/stream", response_model=StreamResponse)
async def get_stream(
    commodity_id: str,
    from_: Annotated[str | None, Query(alias="from", description="조회 시작 월 (YYYY-MM)")] = None,
    to: Annotated[str | None, Query(description="조회 종료 월 (YYYY-MM)")] = None,
    granularity: Annotated[str, Query(description="집계 단위 (monthly/quarterly/yearly)")] = "monthly",
    segments: Annotated[str | None, Query(description="구간 필터 (콤마 구분, 예: A,B)")] = None,
    grade: Annotated[str, Query(description="신뢰도 등급 필터 (콤마 구분)")] = "high,medium",
    patterns: Annotated[str, Query(description="패턴 필터 (콤마 구분)")] = "pattern1,pattern2,pattern3",
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamResponse:
    """스트림 그래프 시계열 + 이상 노드 — Redis TTL 캐싱 적용 (feature_spec_BE-REDIS_v2 §3.3)."""
    # 캐시 키: {prefix}:stream:{commodity_id}:{segment_id}:{from}:{to}:{granularity}
    # segments/grade/patterns는 캐시 키 구분자로 포함 (§3.3 spec의 segment_id에 대응)
    seg_key = segments or "all"
    cache_key = (
        f"{settings.redis_cache_prefix}:stream:"
        f"{commodity_id}:{seg_key}:{from_ or 'default'}:{to or 'default'}:{granularity}"
    )

    # ── Cache HIT 경로 ──────────────────────────────────────────────────────
    cached = await cache_get(redis, cache_key)
    if cached is not None:
        try:
            result = StreamResponse.model_validate(cached)
            logger.info(
                "cache=hit",
                extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
            )
            return result
        except ValidationError as e:
            # PARSE-REDIS-001: API 레이어에서 Pydantic 검증 실패 → 캐시 무효화 후 DB 재조회
            logger.warning(
                "Redis 캐시값 Pydantic 검증 실패 — 캐시 무효화 후 DB 재조회 (PARSE-REDIS-001)",
                extra={
                    "error_code": "PARSE-REDIS-001",
                    "context": {
                        "cache_key": cache_key,
                        "error_msg": str(e),
                    },
                },
            )
            await cache_delete(redis, cache_key)

    # ── Cache MISS 경로 — DB 조회 후 캐시 적재 ─────────────────────────────
    logger.info(
        "cache=miss",
        extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
    )
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    result = await stream_svc.get_stream(
        db=db,
        commodity_id=commodity_id,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        route_type=commodity.route_type,
        commodity_segments=commodity.segments,
        from_str=from_,
        to_str=to,
        granularity=granularity,
        segments_str=segments,
        grade_str=grade,
        patterns_str=patterns,
    )
    await cache_set(redis, cache_key, result.model_dump(mode="json"), ttl=settings.redis_ttl)
    return result


@router.get("/commodities/{commodity_id}/stream/minimap", response_model=StreamMinimapResponse)
async def get_stream_minimap(
    commodity_id: str,
    segments: Annotated[str | None, Query(description="구간 필터 (콤마 구분)")] = None,
    db: AsyncSession = Depends(get_db),
) -> StreamMinimapResponse:
    """스트림 미니맵 — 전체 기간 yearly 고정 + 연도별 이상 밀도."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    return await stream_svc.get_stream_minimap(
        db=db,
        commodity_id=commodity_id,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        commodity_segments=commodity.segments,
        segments_str=segments,
    )


@router.get("/commodities/{commodity_id}/scatter", response_model=ScatterResponse)
async def get_scatter(
    commodity_id: str,
    segment: Annotated[str, Query(description="분석 구간 (단일, 필수)")],
    from_: Annotated[str | None, Query(alias="from", description="조회 시작 월 (YYYY-MM)")] = None,
    to: Annotated[str | None, Query(description="조회 종료 월 (YYYY-MM)")] = None,
    until: Annotated[str | None, Query(description="슬라이더 기준 월 (YYYY-MM)")] = None,
    grade: Annotated[str, Query(description="신뢰도 등급 필터 (콤마 구분)")] = "high,medium",
    db: AsyncSession = Depends(get_db),
) -> ScatterResponse:
    """전달 구조 산점도 — stat_timeseries + baselines 실 DB 조회."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    return await scatter_svc.get_scatter(
        db=db,
        commodity_id=commodity_id,
        segment_id=segment,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        commodity_segments=commodity.segments,
        from_str=from_,
        to_str=to,
        until_str=until,
        grade_str=grade,
    )


@router.get("/commodities/{commodity_id}/raw-prices", response_model=RawPricesResponse)
async def get_raw_prices(
    commodity_id: str,
    layout: Annotated[int, Query(ge=1, le=6, description="레이아웃 번호 1~6")] = 1,
    from_: Annotated[str | None, Query(alias="from", description="조회 시작 월 (YYYY-MM)")] = None,
    to: Annotated[str | None, Query(description="조회 종료 월 (YYYY-MM)")] = None,
    granularity: Annotated[str, Query(description="집계 단위 (monthly/quarterly/yearly)")] = "monthly",
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RawPricesResponse:
    """원시 시계열 레이아웃 1~6 — Redis TTL 캐싱 적용 (feature_spec_BE-REDIS_v2 §3.3)."""
    # 캐시 키: {prefix}:raw-prices:{commodity_id}:{segment_id}:{from}:{to}:{granularity}:{layout}
    cache_key = (
        f"{settings.redis_cache_prefix}:raw-prices:"
        f"{commodity_id}:all:{from_ or 'default'}:{to or 'default'}:{granularity}:{layout}"
    )

    # ── Cache HIT 경로 ──────────────────────────────────────────────────────
    cached = await cache_get(redis, cache_key)
    if cached is not None:
        try:
            result = RawPricesResponse.model_validate(cached)
            logger.info(
                "cache=hit",
                extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
            )
            return result
        except ValidationError as e:
            # PARSE-REDIS-001
            logger.warning(
                "Redis 캐시값 Pydantic 검증 실패 — 캐시 무효화 후 DB 재조회 (PARSE-REDIS-001)",
                extra={
                    "error_code": "PARSE-REDIS-001",
                    "context": {
                        "cache_key": cache_key,
                        "error_msg": str(e),
                    },
                },
            )
            await cache_delete(redis, cache_key)

    # ── Cache MISS 경로 ─────────────────────────────────────────────────────
    logger.info(
        "cache=miss",
        extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
    )
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    result = await rp_svc.get_raw_prices(
        db=db,
        commodity_id=commodity_id,
        route_type=commodity.route_type,
        commodity_segments=commodity.segments,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        layout=layout,
        from_str=from_,
        to_str=to,
        granularity=granularity,
    )
    await cache_set(redis, cache_key, result.model_dump(mode="json"), ttl=settings.redis_ttl)
    return result


@router.get("/commodities/{commodity_id}/raw-prices/minimap", response_model=RawPricesMinimapResponse)
async def get_raw_prices_minimap(
    commodity_id: str,
    layout: Annotated[int, Query(ge=1, le=6, description="레이아웃 번호 1~6")] = 1,
    db: AsyncSession = Depends(get_db),
) -> RawPricesMinimapResponse:
    """원시 시계열 미니맵 — 전체 기간 yearly + anomaly_density."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    return await rp_svc.get_raw_prices_minimap(
        db=db,
        commodity_id=commodity_id,
        route_type=commodity.route_type,
        commodity_segments=commodity.segments,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        layout=layout,
    )
