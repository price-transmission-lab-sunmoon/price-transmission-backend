"""/commodities, /commodities/{id}, /stream, /stream/minimap,
/scatter, /raw-prices, /raw-prices/minimap 엔드포인트 (api_spec_vN §참조·시각화 엔드포인트).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import APIError
from app.schemas.commodity import CommodityDetail, CommodityListResponse
from app.schemas.timeseries import (
    RawPricesResponse,
    ScatterBaseline,
    ScatterResponse,
    StreamResponse,
)
from app.services import reference as ref_svc

router = APIRouter()

_DUMMY_ENVELOPE = dict(
    requested_from="2000-01",
    requested_to="2026-03",
    actual_from="2000-01",
    actual_to="2026-03",
    granularity="monthly",
    total_points=0,
)

_SegmentId = Literal["A", "B", "C", "D", "D_prime"]


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


# ── 시각화 엔드포인트 (Frame 단계 더미 응답, feat/be-api-timeseries에서 실 DB 연결) ──

def _validate_segment(commodity_segments: list[str], commodity_id: str, segment_id: str) -> None:
    if segment_id not in commodity_segments:
        raise APIError(
            "API-SEG-001",
            "해당 품목에 존재하지 않는 구간입니다.",
            context={
                "commodity_id": commodity_id,
                "requested_segment": segment_id,
                "available_segments": commodity_segments,
            },
            http_status=400,
            public_code="INVALID_SEGMENT",
        )


@router.get("/commodities/{commodity_id}/stream", response_model=StreamResponse)
async def get_stream(
    commodity_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamResponse:
    """스트림 그래프 시계열 — Frame 단계 빈 응답."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    return StreamResponse(commodity_id=commodity_id, series=[], anomaly_nodes=[], **_DUMMY_ENVELOPE)


@router.get("/commodities/{commodity_id}/stream/minimap", response_model=StreamResponse)
async def get_stream_minimap(
    commodity_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamResponse:
    """스트림 미니맵 — Frame 단계 빈 응답."""
    await ref_svc.get_commodity_detail(db, commodity_id)
    return StreamResponse(
        commodity_id=commodity_id,
        series=[],
        anomaly_nodes=[],
        **{**_DUMMY_ENVELOPE, "granularity": "yearly"},
    )


@router.get("/commodities/{commodity_id}/scatter", response_model=ScatterResponse)
async def get_scatter(
    commodity_id: str,
    segment_id: Annotated[_SegmentId, Query(description="분석 구간 (api_spec_vN §scatter)")],
    db: AsyncSession = Depends(get_db),
) -> ScatterResponse:
    """전달 구조 산점도 — Frame 단계 빈 응답."""
    commodity = await ref_svc.get_commodity_detail(db, commodity_id)
    _validate_segment(commodity.segments, commodity_id, segment_id)
    return ScatterResponse(
        commodity_id=commodity_id,
        segment_id=segment_id,
        upstream_label="국제가 (원화 환산)",
        downstream_label="수입단가",
        baseline=ScatterBaseline(),
        points=[],
        **_DUMMY_ENVELOPE,
    )


@router.get("/commodities/{commodity_id}/raw-prices", response_model=RawPricesResponse)
async def get_raw_prices(
    commodity_id: str,
    layout: Annotated[int, Query(ge=1, le=6, description="레이아웃 번호 1~6 (api_spec_vN §raw-prices)")] = 1,
    db: AsyncSession = Depends(get_db),
) -> RawPricesResponse:
    """원시 시계열 — Frame 단계 빈 응답."""
    await ref_svc.get_commodity_detail(db, commodity_id)
    return RawPricesResponse(
        commodity_id=commodity_id,
        layout=layout,
        series=[],
        transmission_overlay=[],
        anomaly_nodes=[],
        **_DUMMY_ENVELOPE,
    )


@router.get("/commodities/{commodity_id}/raw-prices/minimap", response_model=RawPricesResponse)
async def get_raw_prices_minimap(
    commodity_id: str,
    db: AsyncSession = Depends(get_db),
) -> RawPricesResponse:
    """원시 시계열 미니맵 — Frame 단계 빈 응답."""
    await ref_svc.get_commodity_detail(db, commodity_id)
    return RawPricesResponse(
        commodity_id=commodity_id,
        layout=1,
        series=[],
        transmission_overlay=[],
        anomaly_nodes=[],
        **{**_DUMMY_ENVELOPE, "granularity": "yearly"},
    )
