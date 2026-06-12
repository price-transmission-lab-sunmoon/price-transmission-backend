"""참조 엔드포인트 DB 쿼리 비즈니스 로직.

엔드포인트: /commodities, /commodities/{id}, /segments, /events, /freshness
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError, ParseError
from app.db.models.batch import DataFreshness
from app.db.models.commodity import Commodity, ExternalEvent, Segment
from app.db.models.reference import Baseline, CointegrationResult
from app.schemas.commodity import (
    CommodityDetail,
    CommodityListResponse,
    CommoditySummary,
    SegmentItem,
    SegmentListResponse,
    SegmentMeta,
)
from app.schemas.meta import EventItem, EventListResponse, FreshnessResponse

# 서버 기동 후 첫 조회 시 1회만 계산하는 ETag 캐시
_segments_etag: str | None = None
_events_etag: str | None = None


def _route_type_to_segments(route_type: str) -> list[str]:
    """route_type → segment 목록 반환."""
    if route_type == "3seg":
        return ["A", "B", "D_prime"]
    return ["A", "B", "C", "D"]


def _compute_etag(data: object) -> str:
    """응답 본문 SHA-256 해시 앞 32자."""
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:32]


async def get_commodities(db: AsyncSession) -> CommodityListResponse:
    """commodities 테이블 전체 조회 — GET /commodities."""
    result = await db.execute(select(Commodity).order_by(Commodity.id))
    rows = result.scalars().all()

    items: list[CommoditySummary] = []
    for row in rows:
        if row.analysis_start is None:
            raise APIError(
                "API-COM-002",
                "파이프라인 데이터가 미적재 상태입니다.",
                context={"commodity_id": row.commodity_id, "missing_field": "analysis_start"},
                http_status=500,
                public_code="PIPELINE_DATA_MISSING",
            )
        try:
            items.append(
                CommoditySummary(
                    commodity_id=row.commodity_id,
                    name_kr=row.name_kr,
                    name_en=row.name_en,
                    cluster=row.cluster,
                    has_wholesale=row.has_wholesale,
                    route_type=row.route_type,
                    segments=_route_type_to_segments(row.route_type),
                    analysis_start=row.analysis_start,
                    analysis_end=row.analysis_end,
                    has_anomaly_this_month=False,
                    latest_anomaly_grade=None,
                )
            )
        except Exception as e:
            raise ParseError(
                "PARSE-ENUM-001",
                "commodities cluster/route_type Literal 불일치",
                context={
                    "table": "commodities",
                    "column": "cluster/route_type",
                    "value": f"{row.cluster}/{row.route_type}",
                    "allowed_values": "grain|oil_sugar|tropical|livestock|independent / 3seg|4seg",
                },
                boundary="DB→API",
            ) from e

    return CommodityListResponse(commodities=items)


async def get_commodity_detail(db: AsyncSession, commodity_id: str) -> CommodityDetail:
    """단일 품목 상세 조회 + segment_meta — GET /commodities/{id}."""
    result = await db.execute(
        select(Commodity).where(Commodity.commodity_id == commodity_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise APIError(
            "API-COM-001",
            "요청한 품목을 찾을 수 없습니다.",
            context={"commodity_id": commodity_id},
            http_status=404,
            public_code="COMMODITY_NOT_FOUND",
        )

    if row.analysis_start is None:
        raise APIError(
            "API-COM-002",
            "파이프라인 데이터가 미적재 상태입니다.",
            context={"commodity_id": commodity_id, "missing_field": "analysis_start"},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )

    # subperiod_id IS NULL = 전체 기간 기준선
    baselines_result = await db.execute(
        select(Baseline, Segment)
        .join(Segment, Segment.segment_id == Baseline.segment_id)
        .where(Baseline.commodity_id == commodity_id)
        .where(Baseline.subperiod_id.is_(None))
    )
    baseline_rows = baselines_result.all()

    coint_result = await db.execute(
        select(CointegrationResult)
        .where(CointegrationResult.commodity_id == commodity_id)
    )
    coint_map: dict[str, CointegrationResult] = {
        r.segment_id: r for r in coint_result.scalars().all()
    }

    segment_meta: dict[str, SegmentMeta] = {}
    for baseline, segment in baseline_rows:
        coint = coint_map.get(baseline.segment_id)
        try:
            segment_meta[baseline.segment_id] = SegmentMeta(
                model_type=baseline.model_type,
                cointegrated=coint.cointegrated if coint is not None else None,
                normal_transmission_lag=baseline.normal_transmission_lag,
                transmission_elasticity=float(baseline.transmission_elasticity),
                upstream_label=segment.upstream_label,
                downstream_label=segment.downstream_label,
                warmup_end=baseline.warmup_end,
            )
        except Exception as e:
            raise ParseError(
                "PARSE-ENUM-001",
                "baselines.model_type Pydantic Literal 불일치",
                context={
                    "table": "baselines",
                    "column": "model_type",
                    "value": str(baseline.model_type),
                    "allowed_values": "VAR|VECM",
                },
                boundary="DB→API",
            ) from e

    try:
        return CommodityDetail(
            commodity_id=row.commodity_id,
            name_kr=row.name_kr,
            name_en=row.name_en,
            cluster=row.cluster,
            has_wholesale=row.has_wholesale,
            route_type=row.route_type,
            segments=_route_type_to_segments(row.route_type),
            analysis_start=row.analysis_start,
            analysis_end=row.analysis_end,
            has_anomaly_this_month=False,
            latest_anomaly_grade=None,
            segment_meta=segment_meta,
        )
    except Exception as e:
        raise ParseError(
            "PARSE-ENUM-001",
            "commodities cluster/route_type Pydantic Literal 불일치",
            context={"table": "commodities", "column": "cluster/route_type"},
            boundary="DB→API",
        ) from e


async def get_segments(db: AsyncSession) -> tuple[SegmentListResponse, str]:
    """segments 전체 조회 + ETag 반환 — GET /segments."""
    global _segments_etag

    result = await db.execute(select(Segment).order_by(Segment.id))
    rows = result.scalars().all()

    items = [
        SegmentItem(
            segment_id=r.segment_id,
            label_kr=r.label_kr,
            upstream_label=r.upstream_label,
            downstream_label=r.downstream_label,
            applies_to=r.applies_to,
            pattern1=r.pattern1,
            pattern2=r.pattern2,
            pattern3=r.pattern3,
            ml_applied=r.ml_applied,
        )
        for r in rows
    ]
    response = SegmentListResponse(segments=items)

    if _segments_etag is None:
        _segments_etag = _compute_etag(response.model_dump())

    return response, _segments_etag


async def get_events(db: AsyncSession) -> tuple[EventListResponse, str]:
    """external_events 전체 조회 + ETag 반환 — GET /events."""
    global _events_etag

    result = await db.execute(select(ExternalEvent).order_by(ExternalEvent.id))
    rows = result.scalars().all()

    items = [
        EventItem(
            event_key=r.event_key,
            label_kr=r.label_kr,
            start_date=r.start_date,
            end_date=r.end_date,
            color_hex=r.color_hex,
            commodities=list(r.commodities) if r.commodities else None,
        )
        for r in rows
    ]
    response = EventListResponse(events=items)

    # commodities 필드가 가변적이므로 매 호출 재계산
    _events_etag = _compute_etag(response.model_dump())

    return response, _events_etag


async def get_freshness(db: AsyncSession) -> FreshnessResponse:
    """data_freshness 최신 1행 조회 — GET /freshness."""
    result = await db.execute(
        select(DataFreshness).order_by(DataFreshness.id.desc()).limit(1)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise APIError(
            "API-COM-002",
            "파이프라인 데이터가 미적재 상태입니다.",
            context={"table": "data_freshness", "reason": "행 없음"},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )

    try:
        last_updated_str: str
        if row.last_updated is not None:
            last_updated_str = row.last_updated.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            raise ValueError("last_updated is None")

        return FreshnessResponse(
            data_up_to=row.data_up_to,
            next_run_date=row.next_run_date,
            last_updated=last_updated_str,
        )
    except Exception as e:
        raise ParseError(
            "PARSE-DATE-001",
            "data_freshness 날짜 직렬화 실패",
            context={"table": "data_freshness", "column": "last_updated"},
            boundary="DB→API",
        ) from e
