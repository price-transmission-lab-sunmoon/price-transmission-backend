"""Pydantic DTO — /anomalies/summary, /anomalies/{id}/detail 응답 (api_spec_vN §이상 탐지 엔드포인트)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator


def _date_to_yyyymm(d: date | str | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, date):
        return d.strftime("%Y-%m")
    return d


class AnomalySummaryItem(BaseModel):
    """GET /anomalies/summary 응답 내 단일 이상 항목."""
    model_config = {"populate_by_name": True, "from_attributes": True}

    anomaly_id: int
    commodity_id: str
    commodity_name_kr: str
    segment_id: str
    period: str  # YYYY-MM
    primary_pattern: Literal["pattern1", "pattern2", "pattern3"]
    confidence_grade: Literal["high", "medium", "reference"]
    is_new: bool
    transmission_rate: float | None = None

    @field_validator("period", mode="before")
    @classmethod
    def coerce_period(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymm(v)


class AnomalySummaryResponse(BaseModel):
    reference_month: str  # YYYY-MM
    total_count: int
    prev_month_count: int
    count_diff: int
    anomalies: list[AnomalySummaryItem]


class StatMetrics(BaseModel):
    model_config = {"protected_namespaces": ()}

    transmission_rate: float | None = None
    rolling_mean: float | None = None
    zscore: float | None = None
    zscore_warning: bool = False
    zscore_alert: bool = False
    zscore_threshold_warning: float  # settings.zscore_warning — 서비스 레이어에서 주입
    zscore_threshold_alert: float    # settings.zscore_alert  — 서비스 레이어에서 주입
    q1: float | None = None
    q3: float | None = None
    iqr_lower: float | None = None
    iqr_upper: float | None = None
    iqr_outlier: bool = False
    over_transmission: bool = False
    under_transmission: bool = False
    normal_lag: int | None = None
    actual_lag: int | None = None
    direction_reversal: bool = False
    lag_deviation: bool = False
    pattern1_flag_type: Literal["direction_reversal", "lag_deviation", "both"] | None = None
    ect_or_spread: float | None = None
    ect_type: Literal["ECT", "log_spread"] | None = None
    spread_n3: float | None = None
    alpha_plus: float | None = None
    alpha_minus: float | None = None
    wald_pvalue: float | None = None
    asymmetry_significant: bool | None = None
    rocket_feather_direction: str | None = None
    model_type: Literal["VAR", "VECM"] | None = None
    cointegrated: bool | None = None
    subperiod_index: int | None = None
    bp_dates: list[str] = []


class MLSummary(BaseModel):
    # backend_reply_phase7ml_v2 §2.3 — *_anomaly: 항상 boolean (null 금지)
    ml_vote: int = 0
    ml_detected: bool = False
    if_anomaly: bool = False
    if_score: float | None = None
    if_percentile: float | None = None
    lof_anomaly: bool = False
    lof_score: float | None = None
    lof_percentile: float | None = None
    svm_anomaly: bool = False
    svm_score: float | None = None
    svm_percentile: float | None = None


class JudgmentStep(BaseModel):
    step: int
    label: str
    value: str
    passed: bool


class AnomalyDetailResponse(BaseModel):
    anomaly_id: int
    commodity_id: str
    commodity_name_kr: str
    segment_id: str
    segment_label_kr: str
    period: str  # YYYY-MM
    primary_pattern: Literal["pattern1", "pattern2", "pattern3"]
    pattern_types: list[Literal["pattern1", "pattern2", "pattern3"]]
    confidence_grade: Literal["high", "medium", "reference"]
    is_new: bool
    stat_metrics: StatMetrics
    ml_summary: MLSummary
    judgment_path: list[JudgmentStep]
