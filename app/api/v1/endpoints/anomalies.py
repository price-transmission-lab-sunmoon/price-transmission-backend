"""/anomalies/summary, /anomalies/{id}/detail, /stat-series,
/stat-snapshot, /irf, /ml-map 엔드포인트 (api_spec_vN §패널·요약 엔드포인트).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.exceptions import APIError
from app.schemas.anomaly import (
    AnomalyDetailResponse,
    AnomalySummaryResponse,
)
from app.services.anomaly_summary import get_anomaly_summary as _get_anomaly_summary
from app.schemas.panel import (
    IRFResponse,
    MLMapResponse,
    StatSnapshotAsymmetryResponse,
    StatSnapshotIQRResponse,
)
from app.schemas.timeseries import StatSeriesResponse

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
async def get_anomaly_summary(
    grade: Annotated[
        str,
        Query(description="신뢰도 등급 필터. 콤마 구분 복수 지정 (high, medium, reference)"),
    ] = "high,medium",
    month: Annotated[
        str | None,
        Query(
            description="기준 월 (YYYY-MM). 미지정 시 data_freshness 최신 기준 월 사용",
            pattern=r"^\d{4}-\d{2}$",
        ),
    ] = None,
) -> AnomalySummaryResponse:
    """이달의 이상 요약 배너 — feature_spec_API-ANO_v7 §1.

    더미 단계: grade·month 파라미터 검증 후 고정값 반환.
    실제 연동: feat/phase7-stat 완료 후 서비스 로직 전환.
    """
    return await _get_anomaly_summary(month=month, grade_str=grade)


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
) -> StatSeriesResponse:
    """지표별 인라인 시계열 — Frame 단계 빈 응답 (api_spec_vN §stat-series).

    metric=iqr 또는 metric=asymmetry 요청 시 SNAPSHOT_METRIC_ON_SERIES 반환
    (비시계열 지표는 /stat-snapshot 사용).
    """
    return StatSeriesResponse(
        anomaly_id=anomaly_id,
        commodity_id="",
        segment_id="",
        metric=metric,
        highlight_period="2026-03",
        data=[],
        **_DUMMY_ENVELOPE,
    )


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
