"""Pydantic DTO — 패널 엔드포인트 응답 스키마 (api_spec_vN §패널 엔드포인트).

/anomalies/{id}/stat-snapshot  — 비시계열 지표 스냅샷 (IQR 박스플롯·비대칭 히스토그램)
/anomalies/{id}/irf            — IRF 차트 데이터
/anomalies/{id}/ml-map         — ML 결과맵 2D 투영 데이터
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class StatSnapshotIQRResponse(BaseModel):
    """metric=iqr — 롤링 IQR 박스플롯 데이터 (api_spec_vN §stat-snapshot)."""
    anomaly_id: int
    metric: Literal["iqr"]
    period: str                     # YYYY-MM
    q1: float | None = None
    median: float | None = None
    q3: float | None = None
    iqr_lower: float | None = None
    iqr_upper: float | None = None
    current_value: float | None = None
    window_months: int = 48


class StatSnapshotAsymmetryResponse(BaseModel):
    """metric=asymmetry — 상승/하락 전이율 분포 히스토그램 데이터 (api_spec_vN §stat-snapshot)."""
    model_config = {"protected_namespaces": ()}

    anomaly_id: int
    metric: Literal["asymmetry"]
    model_type: Literal["TECM", "asymmetric_VAR"] | None = None
    up_samples: list[float] = []
    down_samples: list[float] = []
    alpha_plus: float | None = None
    alpha_minus: float | None = None
    wald_pvalue: float | None = None
    asymmetry_significant: bool | None = None


StatSnapshotResponse = Annotated[
    StatSnapshotIQRResponse | StatSnapshotAsymmetryResponse,
    Field(discriminator="metric"),
]


class IRFDataPoint(BaseModel):
    """IRF 곡선 단일 포인트 (api_spec_vN §irf)."""
    horizon: int
    irf_downstream: float | None = None
    irf_lower_ci: float | None = None
    irf_upper_ci: float | None = None


class IRFCurve(BaseModel):
    """전체 기간 또는 하위 기간별 IRF 곡선 (api_spec_vN §irf)."""
    scope: Literal["full", "subperiod"]
    label: str
    estimation_start: str | None = None   # YYYY-MM
    estimation_end: str | None = None     # YYYY-MM
    subperiod_index: int | None = None    # scope=="subperiod" 일 때만
    peak_horizon: int | None = None
    peak_magnitude: float | None = None
    data: list[IRFDataPoint] = []


class IRFResponse(BaseModel):
    """GET /anomalies/{id}/irf 응답 (api_spec_vN §irf)."""
    commodity_id: str
    segment_id: str
    irfs: list[IRFCurve] = []


class MLMapPoint(BaseModel):
    """ML 결과맵 단일 투영 포인트 (api_spec_vN §ml-map)."""
    period: str                          # YYYY-MM
    x_value: float | None = None
    y_value: float | None = None
    anomaly_score: float | None = None
    is_anomaly: bool = False
    is_highlight: bool = False


class MLMapResponse(BaseModel):
    """GET /anomalies/{id}/ml-map 응답 (api_spec_vN §ml-map).

    OI-15 보류: projection_method 기본값·축 확정은 S4 스프린트 내.
    """
    anomaly_id: int
    commodity_id: str
    segment_id: str
    model: Literal["isolation_forest", "lof", "ocsvm"]
    projection_method: Literal["pca", "feature_direct"] = "pca"
    x_label: str = "PC1"
    y_label: str = "PC2"
    total_points: int = 0
    points: list[MLMapPoint] = []
