"""/anomalies/summary, /anomalies/{id}/detail, /stat-series,
/stat-snapshot, /irf, /ml-map 엔드포인트 (api_spec_vN §패널·요약 엔드포인트).
"""
from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from app.api.deps import get_redis
from app.cache.redis import cache_delete, cache_get, cache_set
from app.core.config import settings
from app.core.exceptions import APIError
from app.schemas.anomaly import (
    AnomalyDetailResponse,
    AnomalySummaryResponse,
)
from app.schemas.panel import (
    IRFResponse,
    MLMapResponse,
    StatSnapshotAsymmetryResponse,
    StatSnapshotIQRResponse,
)
from app.schemas.timeseries import StatSeriesResponse

import redis.asyncio as aioredis

logger = logging.getLogger("app")
router = APIRouter()

_DUMMY_ENVELOPE = dict(
    requested_from="2000-01",
    requested_to="2026-03",
    actual_from="2000-01",
    actual_to="2026-03",
    granularity="monthly",
    total_points=0,
)

# stat-series 지원 metric 값 목록 (api_spec_vN §stat-series)
_STAT_SERIES_METRICS = Literal["transmission_rate", "zscore", "ect", "breakpoints"]

# stat-snapshot은 metric에 따라 응답 스키마가 달라 Union으로 분기
# (Union 응답은 FastAPI response_model 단일 지정이 불가하므로 직접 반환)


@router.get("/anomalies/summary", response_model=AnomalySummaryResponse)
async def get_anomaly_summary() -> AnomalySummaryResponse:
    """이달의 이상 요약 배너 — Frame 단계 빈 응답."""
    return AnomalySummaryResponse(
        reference_month="2026-03",
        total_count=0,
        prev_month_count=0,
        count_diff=0,
        anomalies=[],
    )


@router.get("/anomalies/{anomaly_id}/detail", response_model=AnomalyDetailResponse)
async def get_anomaly_detail(anomaly_id: int) -> AnomalyDetailResponse:
    """분석 수치 패널 통합 — Frame 단계 404 반환 (실 DB 연결은 feat/be-api-panel)."""
    raise APIError(
        "API-ANO-001",
        "요청한 이상 탐지 결과를 찾을 수 없습니다.",
        context={"anomaly_id": anomaly_id},
        http_status=404,
        public_code="ANOMALY_NOT_FOUND",
    )


@router.get("/anomalies/{anomaly_id}/stat-series", response_model=StatSeriesResponse)
async def get_stat_series(
    anomaly_id: int,
    metric: Annotated[_STAT_SERIES_METRICS, Query(description="지표 종류")] = "transmission_rate",
    from_: Annotated[str | None, Query(alias="from", description="조회 시작 월 (YYYY-MM)")] = None,
    to: Annotated[str | None, Query(description="조회 종료 월 (YYYY-MM)")] = None,
    granularity: Annotated[str, Query(description="집계 단위 (monthly/quarterly/yearly)")] = "monthly",
    redis: aioredis.Redis = Depends(get_redis),
) -> StatSeriesResponse:
    """지표별 인라인 시계열 — Redis TTL 캐싱 적용 (feature_spec_BE-REDIS_v2 §3.3).

    metric=iqr 또는 metric=asymmetry 요청 시 SNAPSHOT_METRIC_ON_SERIES 반환
    (비시계열 지표는 /stat-snapshot 사용).
    """
    # 캐시 키: {prefix}:stat-series:{anomaly_id}:{from}:{to}:{granularity}
    # metric도 포함하여 지표별 캐시 분리
    cache_key = (
        f"{settings.redis_cache_prefix}:stat-series:"
        f"{anomaly_id}:{metric}:{from_ or 'default'}:{to or 'default'}:{granularity}"
    )

    # ── Cache HIT 경로 ──────────────────────────────────────────────────────
    cached = await cache_get(redis, cache_key)
    if cached is not None:
        try:
            result = StatSeriesResponse.model_validate(cached)
            logger.info(
                "cache=hit",
                extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
            )
            return result
        except ValidationError as e:
            # PARSE-REDIS-001: API 레이어에서 Pydantic 검증 실패
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

    # ── Cache MISS 경로 — 서비스 조회 후 캐시 적재 ──────────────────────────
    logger.info(
        "cache=miss",
        extra={"error_code": "CACHE", "context": {"cache_key": cache_key}},
    )
    result = StatSeriesResponse(
        anomaly_id=anomaly_id,
        commodity_id="",
        segment_id="",
        metric=metric,
        highlight_period="2026-03",
        data=[],
        **_DUMMY_ENVELOPE,
    )
    await cache_set(redis, cache_key, result.model_dump(mode="json"), ttl=settings.redis_ttl)
    return result


@router.get("/anomalies/{anomaly_id}/stat-snapshot")
async def get_stat_snapshot(
    anomaly_id: int,
    metric: Annotated[Literal["iqr", "asymmetry"], Query(description="지표 종류")] = "iqr",
) -> StatSnapshotIQRResponse | StatSnapshotAsymmetryResponse:
    """비시계열 지표 스냅샷 — Frame 단계 빈 응답 (api_spec_vN §stat-snapshot).

    metric=iqr  → StatSnapshotIQRResponse
    metric=asymmetry → StatSnapshotAsymmetryResponse
    """
    if metric == "iqr":
        return StatSnapshotIQRResponse(
            anomaly_id=anomaly_id,
            metric="iqr",
            period="2026-03",
        )
    return StatSnapshotAsymmetryResponse(
        anomaly_id=anomaly_id,
        metric="asymmetry",
    )


@router.get("/anomalies/{anomaly_id}/irf", response_model=IRFResponse)
async def get_irf(
    anomaly_id: int,  # noqa: ARG001 — feat 단계에서 DB 조회에 사용
    include_subperiods: bool = True,
) -> IRFResponse:
    """IRF 차트 — Frame 단계 빈 응답 (api_spec_vN §irf)."""
    return IRFResponse(commodity_id="", segment_id="", irfs=[])


@router.get("/anomalies/{anomaly_id}/ml-map", response_model=MLMapResponse)
async def get_ml_map(
    anomaly_id: int,
    model: Annotated[
        Literal["isolation_forest", "lof", "ocsvm"],
        Query(description="ML 모델 종류"),
    ] = "isolation_forest",
    projection_method: Annotated[
        Literal["pca", "feature_direct"],
        Query(description="투영 방식 (OI-15 보류)"),
    ] = "pca",
) -> MLMapResponse:
    """ML 결과맵 — Frame 단계 빈 응답 (api_spec_vN §ml-map)."""
    return MLMapResponse(
        anomaly_id=anomaly_id,
        commodity_id="",
        segment_id="",
        model=model,
        projection_method=projection_method,
        x_label="PC1",
        y_label="PC2",
        total_points=0,
        points=[],
    )
