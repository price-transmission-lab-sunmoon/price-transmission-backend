"""Pydantic DTO — /meta/config, /freshness, /events, /meta/pipeline, /meta/analysis-params 응답 (api_spec_vN §방법론 엔드포인트)."""
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


def _date_to_yyyymmdd(d: date | str | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return d


class MetaConfigResponse(BaseModel):
    """GET /meta/config — 헬스체크 (frame 단계 신설, §8.2)."""
    app_env: Literal["development", "production"]
    db_status: Literal["ok", "down"]
    redis_status: Literal["ok", "down"]
    frame_version: str


class FreshnessResponse(BaseModel):
    """GET /freshness 응답."""
    data_up_to: str        # YYYY-MM
    next_run_date: str     # YYYY-MM-DD
    last_updated: str      # ISO 8601 UTC

    @field_validator("data_up_to", mode="before")
    @classmethod
    def coerce_data_up_to(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymm(v)

    @field_validator("next_run_date", mode="before")
    @classmethod
    def coerce_next_run(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymmdd(v)


class EventItem(BaseModel):
    """GET /events 응답 내 단일 이벤트."""
    model_config = {"populate_by_name": True, "from_attributes": True}

    event_key: str
    label_kr: str
    start_date: str    # YYYY-MM
    end_date: str      # YYYY-MM
    color_hex: str
    # v2 (2026-05-21): 사건이 영향을 미치는 품목 목록. NULL/생략 = 전 품목.
    commodities: list[str] | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def coerce_date(cls, v: date | str | None) -> str | None:
        return _date_to_yyyymm(v)


class EventListResponse(BaseModel):
    events: list[EventItem]


# ── /meta/pipeline, /meta/analysis-params (정적 응답) ─────────────────────────

class PipelineNode(BaseModel):
    id: str
    label: str
    description: str
    phase_number: float


class PipelineEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class MetaPipelineResponse(BaseModel):
    version: str
    nodes: list[PipelineNode]
    edges: list[PipelineEdge]


class PatternInfo(BaseModel):
    pattern_id: str
    label_kr: str
    description: str
    applicable_segments: list[str]


class AnalysisParams(BaseModel):
    """GET /meta/analysis-params 응답 내 params 객체 (api_spec_v5 §/meta/analysis-params)."""
    rolling_window: int
    zscore_warning: float
    zscore_alert: float
    iqr_multiplier: float
    stability_threshold: float
    pattern3_n_values: list[int]
    min_subperiod_obs: int
    lag_search_range: list[int]
    chow_test_points: list[str]    # YYYY-MM


class MetaAnalysisParamsResponse(BaseModel):
    version: str
    params: AnalysisParams
    patterns: list[PatternInfo]


class BatchTriggerResponse(BaseModel):
    """POST /admin/batch/trigger 202 Accepted 응답 (feature_spec_BE-BATCH_v2 §3.2)."""
    run_id: int
    status: Literal["running", "completed", "failed"]
    run_date: str   # YYYY-MM-DD
    started_at: str  # ISO 8601 UTC
