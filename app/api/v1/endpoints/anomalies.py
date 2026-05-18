"""/anomalies/summary, /anomalies/{id}/detail, /stat-series,
/stat-snapshot, /irf, /ml-map 엔드포인트 (api_spec_vN §패널·요약 엔드포인트).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
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
from app.services import anomaly_panel

router = APIRouter()

# iq r·asymmetry 를 포함한 전체 허용 목록 — 서비스에서 SNAPSHOT_METRIC_ON_SERIES 분기
# (Literal 제한 후 FastAPI 422 대신 명세 §5.1 API-MET-002 형식으로 반환)
_StatSeriesMetric = Literal[
    "transmission_rate", "zscore", "ect", "breakpoints", "iqr", "asymmetry"
]


@router.get("/anomalies/summary", response_model=AnomalySummaryResponse)
async def get_anomaly_summary() -> AnomalySummaryResponse:
    """이달의 이상 요약 배너 — feat/be-api-anomaly 브랜치에서 실 DB 연결 예정."""
    return AnomalySummaryResponse(
        reference_month="2026-03",
        total_count=0,
        prev_month_count=0,
        count_diff=0,
        anomalies=[],
    )


@router.get("/anomalies/{anomaly_id}/detail", response_model=AnomalyDetailResponse)
async def get_anomaly_detail(
    anomaly_id: int,
    db: AsyncSession = Depends(get_db),
) -> AnomalyDetailResponse:
    """분석 수치 패널 통합 (api_spec_vN §/detail).

    예외: API-ANO-001 (404 미존재), API-ANO-002 (500 파이프라인 누락), API-INT-001 (500)
    """
    return await anomaly_panel.get_detail(anomaly_id, db)


@router.get("/anomalies/{anomaly_id}/stat-series", response_model=StatSeriesResponse)
async def get_stat_series(
    anomaly_id: int,
    metric: Annotated[_StatSeriesMetric, Query(description="지표 종류")] = "transmission_rate",
    from_: Annotated[
        str | None, Query(alias="from", description="조회 시작 월 (YYYY-MM)")
    ] = None,
    to: Annotated[str | None, Query(description="조회 종료 월 (YYYY-MM)")] = None,
    granularity: Annotated[
        Literal["monthly", "quarterly", "yearly"],
        Query(description="집계 단위"),
    ] = "monthly",
    db: AsyncSession = Depends(get_db),
) -> StatSeriesResponse:
    """지표별 인라인 시계열 (api_spec_vN §stat-series).

    - metric=iqr·asymmetry → SNAPSHOT_METRIC_ON_SERIES 400
    - from > to → INVALID_DATE_RANGE 400
    예외: API-MET-001, API-MET-002, API-STR-002, API-ANO-001, API-INT-001
    """
    return await anomaly_panel.get_stat_series(
        anomaly_id=anomaly_id,
        metric=metric,
        from_str=from_,
        to_str=to,
        granularity=granularity,
        session=db,
    )


@router.get("/anomalies/{anomaly_id}/stat-snapshot")
async def get_stat_snapshot(
    anomaly_id: int,
    metric: Annotated[Literal["iqr", "asymmetry"], Query(description="지표 종류")] = "iqr",
    db: AsyncSession = Depends(get_db),
) -> StatSnapshotIQRResponse | StatSnapshotAsymmetryResponse:
    """비시계열 지표 스냅샷 (api_spec_vN §stat-snapshot).

    metric=iqr  → StatSnapshotIQRResponse (롤링 IQR 박스플롯)
    metric=asymmetry → StatSnapshotAsymmetryResponse (상승/하락 전이율 히스토그램)
    예외: API-MET-003 (FastAPI 422→API-VAL-001), API-ANO-001, API-ANO-002, API-INT-001
    """
    if metric == "iqr":
        return await anomaly_panel.get_stat_snapshot_iqr(anomaly_id, db)
    return await anomaly_panel.get_stat_snapshot_asymmetry(anomaly_id, db)


@router.get("/anomalies/{anomaly_id}/irf", response_model=IRFResponse)
async def get_irf(
    anomaly_id: int,
    include_subperiods: Annotated[
        bool, Query(description="하위 기간별 IRF 포함 여부")
    ] = True,
    db: AsyncSession = Depends(get_db),
) -> IRFResponse:
    """IRF 차트 데이터 (api_spec_vN §irf).

    전체 기간 + include_subperiods=true 시 하위 기간별 IRF 곡선·CI 포함.
    예외: API-ANO-001, API-INT-001
    """
    return await anomaly_panel.get_irf(anomaly_id, include_subperiods, db)


@router.get("/anomalies/{anomaly_id}/ml-map", response_model=MLMapResponse)
async def get_ml_map(
    anomaly_id: int,
    model: Annotated[
        Literal["isolation_forest", "lof", "ocsvm"],
        Query(description="ML 모델 종류"),
    ] = "isolation_forest",
    projection_method: Annotated[
        Literal["pca", "feature_direct"],
        Query(description="투영 방식 (OI-15 보류 — 현재 pca 고정)"),
    ] = "pca",
    db: AsyncSession = Depends(get_db),
) -> MLMapResponse:
    """ML 결과맵 2D 투영 데이터 (api_spec_vN §ml-map).

    OI-15 보류: projection_method 기본값·축 확정은 S4 내.
    예외: API-ANO-001, API-ANO-003 (ML 미산출 404), API-INT-001
    """
    return await anomaly_panel.get_ml_map(anomaly_id, model, projection_method, db)
