"""Pydantic DTO — /commodities, /commodities/{id}, /segments 응답 (api_spec_vN 1:1 대응)."""
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


class CommoditySummary(BaseModel):
    """GET /commodities 응답 — 품목 목록 단일 항목."""
    model_config = {"populate_by_name": True, "from_attributes": True}

    commodity_id: str
    name_kr: str
    name_en: str
    cluster: Literal["grain", "oil_sugar", "tropical", "livestock", "independent"]
    has_wholesale: bool
    route_type: Literal["3seg", "4seg"]
    segments: list[str]
    analysis_start: str | None = None   # YYYY-MM
    analysis_end: str | None = None     # YYYY-MM
    has_anomaly_this_month: bool = False
    latest_anomaly_grade: Literal["high", "medium", "reference"] | None = None

    @field_validator("analysis_start", "analysis_end", mode="before")
    @classmethod
    def coerce_period(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymm(v)


class CommodityListResponse(BaseModel):
    commodities: list[CommoditySummary]


class SegmentMeta(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_type: Literal["VAR", "VECM"] | None = None
    cointegrated: bool | None = None
    normal_transmission_lag: int | None = None
    transmission_elasticity: float | None = None
    upstream_label: str | None = None
    downstream_label: str | None = None
    warmup_end: str | None = None   # YYYY-MM

    @field_validator("warmup_end", mode="before")
    @classmethod
    def coerce_warmup(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymm(v)


class CommodityDetail(CommoditySummary):
    """GET /commodities/{id} 응답 — 단일 품목 상세."""
    segment_meta: dict[str, SegmentMeta] = {}


class SegmentItem(BaseModel):
    """GET /segments 응답 — 단일 구간 항목."""
    model_config = {"populate_by_name": True, "from_attributes": True}

    segment_id: str
    label_kr: str
    upstream_label: str
    downstream_label: str
    applies_to: str
    pattern1: bool
    pattern2: bool
    pattern3: bool
    ml_applied: bool


class SegmentListResponse(BaseModel):
    segments: list[SegmentItem]
