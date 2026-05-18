"""Pydantic DTO — 시계열 응답 envelope + /stream, /scatter, /raw-prices, /stat-series (api_spec_vN §시계열 엔드포인트)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator


def _validate_period(v: str | date | None) -> str | None:
    """YYYY-MM 형식 강제. date → YYYY-MM 변환."""
    if v is None:
        return None
    if isinstance(v, date):
        return v.strftime("%Y-%m")
    # 문자열 검증
    import re
    if re.fullmatch(r"\d{4}-\d{2}", v):
        return v
    raise ValueError(f"period는 YYYY-MM 형식이어야 합니다: {v!r}")


# ── 공통 envelope ─────────────────────────────────────────────────────────────

class TimeseriesEnvelope(BaseModel):
    requested_from: str
    requested_to: str
    actual_from: str
    actual_to: str
    granularity: Literal["monthly", "quarterly", "yearly"]
    total_points: int

    @field_validator("requested_from", "requested_to", "actual_from", "actual_to", mode="before")
    @classmethod
    def coerce_period(cls, v: str | date | None) -> str | None:
        return _validate_period(v)


# ── /stream ───────────────────────────────────────────────────────────────────

class StreamDataPoint(BaseModel):
    period: str
    transmission_rate: float | None = None
    upstream_pct: float | None = None
    downstream_pct: float | None = None
    in_warmup_period: bool = False
    has_anomaly: bool = False
    anomaly_ids: list[int] = []

    @field_validator("period", mode="before")
    @classmethod
    def coerce_period(cls, v: str | date | None) -> str | None:
        return _validate_period(v)


class StreamSeries(BaseModel):
    segment_id: str
    data: list[StreamDataPoint]


class AnomalyNode(BaseModel):
    anomaly_id: int
    segment_id: str
    period: str
    primary_pattern: Literal["pattern1", "pattern2", "pattern3"]
    pattern_types: list[Literal["pattern1", "pattern2", "pattern3"]]
    confidence_grade: Literal["high", "medium", "reference"]
    transmission_rate: float | None = None
    is_new: bool


class StreamResponse(TimeseriesEnvelope):
    commodity_id: str
    series: list[StreamSeries]
    anomaly_nodes: list[AnomalyNode]


# ── /scatter ──────────────────────────────────────────────────────────────────

class ScatterPoint(BaseModel):
    period: str
    upstream_pct: float | None = None
    downstream_pct: float | None = None
    is_anomaly: bool = False
    anomaly_id: int | None = None
    confidence_grade: Literal["high", "medium", "reference"] | None = None
    primary_pattern: Literal["pattern1", "pattern2", "pattern3"] | None = None


class ScatterBaseline(BaseModel):
    transmission_elasticity: float | None = None
    normal_transmission_lag: int | None = None


class ScatterResponse(TimeseriesEnvelope):
    commodity_id: str
    segment_id: str
    upstream_label: str
    downstream_label: str
    until: str | None = None
    baseline: ScatterBaseline
    points: list[ScatterPoint]


# ── /raw-prices ───────────────────────────────────────────────────────────────

class RawPriceDataPoint(BaseModel):
    period: str
    value: float | None = None
    index_2020: float | None = None
    has_anomaly: bool = False
    anomaly_ids: list[int] = []


class RawPriceSeries(BaseModel):
    source: str
    label_kr: str
    color_hint: str
    data: list[RawPriceDataPoint]


class TransmissionOverlaySeries(BaseModel):
    segment_id: str
    data: list[StreamDataPoint]


class RawPriceAnomalyNode(BaseModel):
    anomaly_id: int
    segment_id: str
    period: str
    confidence_grade: Literal["high", "medium", "reference"]
    primary_pattern: Literal["pattern1", "pattern2", "pattern3"]
    is_new: bool


class RawPricesResponse(TimeseriesEnvelope):
    commodity_id: str
    layout: int
    series: list[RawPriceSeries]
    transmission_overlay: list[TransmissionOverlaySeries]
    anomaly_nodes: list[RawPriceAnomalyNode]


# ── /stat-series ─────────────────────────────────────────────────────────────

class StatSeriesPoint(BaseModel):
    period: str
    transmission_rate: float | None = None
    rolling_mean: float | None = None
    q1: float | None = None
    q3: float | None = None
    in_warmup_period: bool = False
    is_breakpoint: bool = False
    zscore: float | None = None
    ect_or_spread: float | None = None
    ect_type: Literal["ECT", "log_spread"] | None = None


class StatSeriesResponse(TimeseriesEnvelope):
    anomaly_id: int
    commodity_id: str
    segment_id: str
    metric: str
    highlight_period: str
    data: list[StatSeriesPoint]


# ── 미니맵 공통 ───────────────────────────────────────────────────────────────

class AnomalyDensityPoint(BaseModel):
    """연도별 이상 밀도 포인트 (mv_anomaly_density_yearly 기준)."""
    period: str          # 연도 문자열 "2022"
    high_count: int
    medium_count: int
    reference_count: int


# ── /stream/minimap ────────────────────────────────────────────────────────────

class StreamMinimapResponse(StreamResponse):
    """스트림 미니맵 응답 — StreamResponse + anomaly_density (api_spec_vN §stream/minimap)."""
    anomaly_density: list[AnomalyDensityPoint] = []


# ── /raw-prices/minimap ───────────────────────────────────────────────────────

class RawPricesMinimapResponse(RawPricesResponse):
    """원시 시계열 미니맵 응답 — RawPricesResponse + anomaly_density (api_spec_vN §raw-prices/minimap)."""
    anomaly_density: list[AnomalyDensityPoint] = []
