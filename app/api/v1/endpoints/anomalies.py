"""/anomalies/summary, /anomalies/{id}/detail, /stat-series, /stat-snapshot, /irf, /ml-map 엔드포인트."""
from fastapi import APIRouter

from app.core.exceptions import APIError
from app.schemas.anomaly import (
    AnomalyDetailResponse,
    AnomalySummaryResponse,
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
async def get_stat_series(anomaly_id: int, metric: str = "transmission_rate") -> StatSeriesResponse:
    """지표별 인라인 시계열 — Frame 단계 빈 응답."""
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
async def get_stat_snapshot(anomaly_id: int, metric: str = "iqr") -> dict:
    """비시계열 지표 스냅샷 — Frame 단계 빈 응답."""
    return {"anomaly_id": anomaly_id, "metric": metric}


@router.get("/anomalies/{anomaly_id}/irf")
async def get_irf(anomaly_id: int) -> dict:
    """IRF 차트 — Frame 단계 빈 응답."""
    return {"commodity_id": "", "segment_id": "", "irfs": []}


@router.get("/anomalies/{anomaly_id}/ml-map")
async def get_ml_map(anomaly_id: int, model: str = "isolation_forest") -> dict:
    """ML 결과맵 — Frame 단계 빈 응답."""
    return {
        "anomaly_id": anomaly_id,
        "commodity_id": "",
        "segment_id": "",
        "model": model,
        "projection_method": "pca",
        "x_label": "PC1",
        "y_label": "PC2",
        "total_points": 0,
        "points": [],
    }
