"""/commodities, /commodities/{id}, /stream, /stream/minimap,
/scatter, /raw-prices, /raw-prices/minimap 엔드포인트 (api_spec_vN §참조·시각화 엔드포인트).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.exceptions import APIError
from app.schemas.commodity import CommodityDetail, CommodityListResponse, CommoditySummary
from app.schemas.timeseries import (
    RawPricesResponse,
    ScatterBaseline,
    ScatterResponse,
    StreamResponse,
)

router = APIRouter()

# db_schema_vN §commodities 초기 데이터 (더미, frame_spec_backend_vN §8.1)
_COMMODITIES: list[dict] = [
    {"commodity_id": "wheat",      "name_kr": "밀",      "name_en": "Wheat",      "cluster": "grain",       "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "maize",      "name_kr": "옥수수",  "name_en": "Maize",      "cluster": "grain",       "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "soybean",    "name_kr": "대두",    "name_en": "Soybean",    "cluster": "grain",       "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "palm_oil",   "name_kr": "팜유",    "name_en": "Palm Oil",   "cluster": "oil_sugar",   "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "sugar",      "name_kr": "설탕",    "name_en": "Sugar",      "cluster": "oil_sugar",   "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "coffee",     "name_kr": "커피",    "name_en": "Coffee",     "cluster": "tropical",    "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "beef",       "name_kr": "소고기",  "name_en": "Beef",       "cluster": "livestock",   "has_wholesale": False, "route_type": "3seg", "segments": ["A", "B", "D_prime"]},
    {"commodity_id": "groundnuts", "name_kr": "땅콩",    "name_en": "Groundnuts", "cluster": "independent", "has_wholesale": True,  "route_type": "4seg", "segments": ["A", "B", "C", "D"]},
    {"commodity_id": "banana",     "name_kr": "바나나",  "name_en": "Banana",     "cluster": "tropical",    "has_wholesale": True,  "route_type": "4seg", "segments": ["A", "B", "C", "D"]},
    {"commodity_id": "orange",     "name_kr": "오렌지",  "name_en": "Orange",     "cluster": "independent", "has_wholesale": True,  "route_type": "4seg", "segments": ["A", "B", "C", "D"]},
]

_COMMODITY_MAP = {c["commodity_id"]: c for c in _COMMODITIES}

_DUMMY_ENVELOPE = dict(
    requested_from="2000-01",
    requested_to="2026-03",
    actual_from="2000-01",
    actual_to="2026-03",
    granularity="monthly",
    total_points=0,
)

_SegmentId = Literal["A", "B", "C", "D", "D_prime"]


def _get_commodity_or_404(commodity_id: str) -> dict:
    """품목 조회 헬퍼 — 없으면 COMMODITY_NOT_FOUND 404."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError(
            "API-COM-001",
            "요청한 품목을 찾을 수 없습니다.",
            context={"commodity_id": commodity_id},
            http_status=404,
            public_code="COMMODITY_NOT_FOUND",
        )
    return _COMMODITY_MAP[commodity_id]


def _validate_segment(commodity: dict, segment_id: str) -> None:
    """구간 유효성 검사 — 해당 품목에 없는 구간이면 INVALID_SEGMENT 400."""
    if segment_id not in commodity["segments"]:
        raise APIError(
            "API-SEG-001",
            "해당 품목에 존재하지 않는 구간입니다.",
            context={
                "commodity_id": commodity["commodity_id"],
                "requested_segment": segment_id,
                "available_segments": commodity["segments"],
            },
            http_status=400,
            public_code="INVALID_SEGMENT",
        )


@router.get("/commodities", response_model=CommodityListResponse)
async def list_commodities() -> CommodityListResponse:
    """품목 목록 — db_schema_vN §commodities 초기 데이터 (10행)."""
    return CommodityListResponse(
        commodities=[CommoditySummary(**c) for c in _COMMODITIES]
    )


@router.get("/commodities/{commodity_id}", response_model=CommodityDetail)
async def get_commodity(commodity_id: str) -> CommodityDetail:
    """단일 품목 상세 — 더미 응답."""
    c = _get_commodity_or_404(commodity_id)
    return CommodityDetail(**c, segment_meta={})


@router.get("/commodities/{commodity_id}/stream", response_model=StreamResponse)
async def get_stream(commodity_id: str) -> StreamResponse:
    """스트림 그래프 시계열 — Frame 단계 빈 응답."""
    _get_commodity_or_404(commodity_id)
    return StreamResponse(commodity_id=commodity_id, series=[], anomaly_nodes=[], **_DUMMY_ENVELOPE)


@router.get("/commodities/{commodity_id}/stream/minimap", response_model=StreamResponse)
async def get_stream_minimap(commodity_id: str) -> StreamResponse:
    """스트림 미니맵 — Frame 단계 빈 응답."""
    _get_commodity_or_404(commodity_id)
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
) -> ScatterResponse:
    """전달 구조 산점도 — Frame 단계 빈 응답 (api_spec_vN §scatter).

    segment_id 필수 파라미터. 해당 품목에 없는 구간 지정 시 INVALID_SEGMENT 400.
    """
    commodity = _get_commodity_or_404(commodity_id)
    _validate_segment(commodity, segment_id)
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
) -> RawPricesResponse:
    """원시 시계열 — Frame 단계 빈 응답 (api_spec_vN §raw-prices).

    layout 1~6 범위 밖 요청 시 FastAPI가 자동으로 422 반환 (INVALID_LAYOUT).
    """
    _get_commodity_or_404(commodity_id)
    return RawPricesResponse(
        commodity_id=commodity_id,
        layout=layout,
        series=[],
        transmission_overlay=[],
        anomaly_nodes=[],
        **_DUMMY_ENVELOPE,
    )


@router.get("/commodities/{commodity_id}/raw-prices/minimap", response_model=RawPricesResponse)
async def get_raw_prices_minimap(commodity_id: str) -> RawPricesResponse:
    """원시 시계열 미니맵 — Frame 단계 빈 응답."""
    _get_commodity_or_404(commodity_id)
    return RawPricesResponse(
        commodity_id=commodity_id,
        layout=1,
        series=[],
        transmission_overlay=[],
        anomaly_nodes=[],
        **{**_DUMMY_ENVELOPE, "granularity": "yearly"},
    )
