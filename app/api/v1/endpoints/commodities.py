"""/commodities, /commodities/{id}, /stream, /stream/minimap, /scatter, /raw-prices 엔드포인트."""
from fastapi import APIRouter

from app.core.exceptions import APIError
from app.schemas.commodity import CommodityDetail, CommodityListResponse, CommoditySummary
from app.schemas.timeseries import (
    RawPricesResponse,
    ScatterBaseline,
    ScatterResponse,
    StreamResponse,
)

router = APIRouter()

# db_schema_v3 §commodities 초기 데이터 (더미, §8.1)
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


@router.get("/commodities", response_model=CommodityListResponse)
async def list_commodities() -> CommodityListResponse:
    """품목 목록 — db_schema_v3 §commodities 초기 데이터 (10행)."""
    return CommodityListResponse(
        commodities=[CommoditySummary(**c) for c in _COMMODITIES]
    )


@router.get("/commodities/{commodity_id}", response_model=CommodityDetail)
async def get_commodity(commodity_id: str) -> CommodityDetail:
    """단일 품목 상세 — 더미 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError(
            "API-COM-001",
            "요청한 품목을 찾을 수 없습니다.",
            context={"commodity_id": commodity_id},
            http_status=404,
            public_code="COMMODITY_NOT_FOUND",
        )
    c = _COMMODITY_MAP[commodity_id]
    return CommodityDetail(**c, segment_meta={})


@router.get("/commodities/{commodity_id}/stream", response_model=StreamResponse)
async def get_stream(commodity_id: str) -> StreamResponse:
    """스트림 그래프 시계열 — Frame 단계 빈 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError("API-COM-001", "요청한 품목을 찾을 수 없습니다.", context={"commodity_id": commodity_id}, http_status=404, public_code="COMMODITY_NOT_FOUND")
    return StreamResponse(commodity_id=commodity_id, series=[], anomaly_nodes=[], **_DUMMY_ENVELOPE)


@router.get("/commodities/{commodity_id}/stream/minimap", response_model=StreamResponse)
async def get_stream_minimap(commodity_id: str) -> StreamResponse:
    """스트림 미니맵 — Frame 단계 빈 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError("API-COM-001", "요청한 품목을 찾을 수 없습니다.", context={"commodity_id": commodity_id}, http_status=404, public_code="COMMODITY_NOT_FOUND")
    return StreamResponse(commodity_id=commodity_id, series=[], anomaly_nodes=[], **{**_DUMMY_ENVELOPE, "granularity": "yearly"})


@router.get("/commodities/{commodity_id}/scatter", response_model=ScatterResponse)
async def get_scatter(commodity_id: str) -> ScatterResponse:
    """전달 구조 산점도 — Frame 단계 빈 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError("API-COM-001", "요청한 품목을 찾을 수 없습니다.", context={"commodity_id": commodity_id}, http_status=404, public_code="COMMODITY_NOT_FOUND")
    return ScatterResponse(
        commodity_id=commodity_id,
        segment_id="A",
        upstream_label="국제가 (원화 환산)",
        downstream_label="수입단가",
        baseline=ScatterBaseline(),
        points=[],
        **_DUMMY_ENVELOPE,
    )


@router.get("/commodities/{commodity_id}/raw-prices", response_model=RawPricesResponse)
async def get_raw_prices(commodity_id: str) -> RawPricesResponse:
    """원시 시계열 — Frame 단계 빈 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError("API-COM-001", "요청한 품목을 찾을 수 없습니다.", context={"commodity_id": commodity_id}, http_status=404, public_code="COMMODITY_NOT_FOUND")
    return RawPricesResponse(commodity_id=commodity_id, layout=1, series=[], transmission_overlay=[], anomaly_nodes=[], **_DUMMY_ENVELOPE)


@router.get("/commodities/{commodity_id}/raw-prices/minimap", response_model=RawPricesResponse)
async def get_raw_prices_minimap(commodity_id: str) -> RawPricesResponse:
    """원시 시계열 미니맵 — Frame 단계 빈 응답."""
    if commodity_id not in _COMMODITY_MAP:
        raise APIError("API-COM-001", "요청한 품목을 찾을 수 없습니다.", context={"commodity_id": commodity_id}, http_status=404, public_code="COMMODITY_NOT_FOUND")
    return RawPricesResponse(commodity_id=commodity_id, layout=1, series=[], transmission_overlay=[], anomaly_nodes=[], **{**_DUMMY_ENVELOPE, "granularity": "yearly"})
