"""/commodities, /commodities/{id}, /stream, /stream/minimap,
/scatter, /raw-prices, /raw-prices/minimap 엔드포인트 (api_spec_vN §참조·시각화 엔드포인트).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
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
) -> StreamResponse:
    """스트림 그래프 시계열 + 이상 노드 — stat_timeseries 실 DB 조회."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    return await stream_svc.get_stream(
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
) -> RawPricesResponse:
    """원시 시계열 레이아웃 1~6 — raw_prices 실 DB 조회."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    analysis_start, analysis_end = _analysis_dates(commodity, commodity_id)
    return await rp_svc.get_raw_prices(
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
