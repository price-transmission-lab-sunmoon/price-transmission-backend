"""스트림 그래프·미니맵 비즈니스 로직 (feature_spec_API-STR_v5 §1.2).

엔드포인트: GET /commodities/{id}/stream
            GET /commodities/{id}/stream/minimap
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.coerce import parse_yyyymm
from app.core.coerce import safe_float as _safe_float
from app.core.coerce import safe_period as _safe_period
from app.core.exceptions import APIError, ParseError
from app.db.models.anomaly import AnomalyResult
from app.db.models.timeseries import MvAnomalyDensityYearly, StatTimeseries
from app.schemas.timeseries import (
    AnomalyNode,
    StreamDataPoint,
    StreamMinimapResponse,
    StreamResponse,
    StreamSeries,
)
from app.services.aggregation import aggregate_by_granularity, build_anomaly_density

# ── 공용 파싱·변환 헬퍼 ────────────────────────────────────────────────────────

def _parse_yyyymm(value: str, field: str) -> date:
    """YYYY-MM → date. 스트림 도메인 코드(API-STR-002) 고정."""
    return parse_yyyymm(value, field, code="API-STR-002")


def _clamp_range(
    from_: date,
    to_: date,
    analysis_start: date,
    analysis_end: date,
    commodity_id: str,
) -> tuple[date, date]:
    """날짜 범위 클램핑.

    - from_ > to_ → API-STR-002 (INVALID_DATE_RANGE)
    - 완전 이탈   → API-STR-003 (INVALID_DATE_RANGE)
    - 부분 이탈   → 클램핑 후 반환
    """
    if from_ > to_:
        raise APIError(
            "API-STR-002",
            "from이 to보다 이후입니다.",
            context={"from": str(from_), "to": str(to_), "commodity_id": commodity_id},
            http_status=400,
            public_code="INVALID_DATE_RANGE",
        )
    if from_ > analysis_end or to_ < analysis_start:
        raise APIError(
            "API-STR-003",
            "요청 범위가 분석 가용 범위를 완전히 벗어났습니다.",
            context={
                "requested_from": str(from_),
                "requested_to": str(to_),
                "analysis_start": str(analysis_start),
                "analysis_end": str(analysis_end),
                "commodity_id": commodity_id,
            },
            http_status=400,
            public_code="INVALID_DATE_RANGE",
        )
    return max(from_, analysis_start), min(to_, analysis_end)


# ── granularity 집계 헬퍼 ─────────────────────────────────────────────────────

# 집계 로직은 app.services.aggregation.aggregate_by_granularity 로 이전


# ── /stream ───────────────────────────────────────────────────────────────────

async def get_stream(
    db: AsyncSession,
    commodity_id: str,
    analysis_start: date,
    analysis_end: date,
    route_type: str,
    commodity_segments: list[str],
    from_str: str | None,
    to_str: str | None,
    granularity: str,
    segments_str: str | None,
    grade_str: str,
    patterns_str: str,
) -> StreamResponse:
    """스트림 그래프 시계열 + 이상 노드 반환 (feature_spec_API-STR_v5 §1.2)."""
    # 1. granularity 검증 (API-STR-004)
    if granularity not in ("monthly", "quarterly", "yearly"):
        raise APIError(
            "API-STR-004",
            "granularity는 monthly / quarterly / yearly 중 하나여야 합니다.",
            context={"granularity": granularity},
            http_status=400,
            public_code="INVALID_GRANULARITY",
        )

    # 2. 구간 필터 파싱 및 검증 (API-SEG-001)
    segments_filter: list[str] = (
        [s.strip() for s in segments_str.split(",") if s.strip()]
        if segments_str
        else list(commodity_segments)
    )
    for seg in segments_filter:
        if seg not in commodity_segments:
            raise APIError(
                "API-SEG-001",
                "해당 품목에 존재하지 않는 구간입니다.",
                context={
                    "commodity_id": commodity_id,
                    "requested_segment": seg,
                    "available_segments": commodity_segments,
                },
                http_status=400,
                public_code="INVALID_SEGMENT",
            )

    # 3. 날짜 파싱 및 클램핑
    requested_from = _parse_yyyymm(from_str, "from") if from_str else analysis_start
    requested_to = _parse_yyyymm(to_str, "to") if to_str else analysis_end
    actual_from, actual_to = _clamp_range(
        requested_from, requested_to, analysis_start, analysis_end, commodity_id
    )

    # 4. 등급·패턴 필터 파싱
    grade_filter = [g.strip() for g in grade_str.split(",") if g.strip()]
    pattern_filter = [p.strip() for p in patterns_str.split(",") if p.strip()]

    # 5. stat_timeseries 조회
    try:
        ts_result = await db.execute(
            select(StatTimeseries)
            .where(
                and_(
                    StatTimeseries.commodity_id == commodity_id,
                    StatTimeseries.segment_id.in_(segments_filter),
                    StatTimeseries.period >= actual_from,
                    StatTimeseries.period <= actual_to,
                )
            )
            .order_by(StatTimeseries.segment_id, StatTimeseries.period)
        )
        ts_rows = ts_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "스트림 시계열 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 6. 이상 노드 조회 (anomaly_results — 항상 월 단위, api_spec_vN §granularity 동작 규칙)
    try:
        anomaly_result = await db.execute(
            select(AnomalyResult)
            .where(
                and_(
                    AnomalyResult.commodity_id == commodity_id,
                    AnomalyResult.segment_id.in_(segments_filter),
                    AnomalyResult.confidence_grade.in_(grade_filter),
                    AnomalyResult.primary_pattern.in_(pattern_filter),
                    AnomalyResult.period >= actual_from,
                    AnomalyResult.period <= actual_to,
                )
            )
            .order_by(AnomalyResult.period)
        )
        anomaly_rows = anomaly_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "스트림 이상 노드 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 7. 이상 노드 인덱스 구성: (segment_id, period) → anomaly_id 목록
    anomaly_index: dict[tuple[str, date], list[int]] = defaultdict(list)
    for ar in anomaly_rows:
        anomaly_index[(ar.segment_id, ar.period)].append(ar.id)

    # 8. warmup 전용 체크 (API-STR-001)
    if ts_rows and all(r.in_warmup_period for r in ts_rows):
        raise APIError(
            "API-STR-001",
            "요청한 기간은 분석 기준 분포 축적 기간입니다.",
            context={"commodity_id": commodity_id, "from": str(actual_from), "to": str(actual_to)},
            http_status=404,
            public_code="WARMUP_PERIOD_ONLY",
        )

    # 9. 구간별 월 단위 포인트 조립
    seg_monthly: dict[str, list[dict]] = defaultdict(list)
    for row in ts_rows:
        ids = anomaly_index.get((row.segment_id, row.period), [])
        seg_monthly[row.segment_id].append({
            "period": row.period,
            "transmission_rate": _safe_float(row.transmission_rate, "stat_timeseries", "transmission_rate"),
            "upstream_pct": _safe_float(row.upstream_pct, "stat_timeseries", "upstream_pct"),
            "downstream_pct": _safe_float(row.downstream_pct, "stat_timeseries", "downstream_pct"),
            "in_warmup_period": bool(row.in_warmup_period),
            "anomaly_ids": ids,
        })

    # 10. granularity 집계 및 StreamSeries 조립
    series: list[StreamSeries] = []
    total_points = 0
    for seg_id in segments_filter:
        monthly = seg_monthly.get(seg_id, [])
        aggregated = aggregate_by_granularity(
            monthly, granularity,
            avg_fields=("transmission_rate", "upstream_pct", "downstream_pct"),
            any_fields=("in_warmup_period",),
            concat_fields=("anomaly_ids",),
        )
        points = [
            StreamDataPoint(
                period=_safe_period(p["period"], "stat_timeseries", "period"),
                transmission_rate=p["transmission_rate"],
                upstream_pct=p["upstream_pct"],
                downstream_pct=p["downstream_pct"],
                in_warmup_period=p["in_warmup_period"],
                has_anomaly=bool(p["anomaly_ids"]),
                anomaly_ids=p["anomaly_ids"],
            )
            for p in aggregated
        ]
        series.append(StreamSeries(segment_id=seg_id, data=points))
        if not total_points and points:
            total_points = len(points)
    if total_points == 0 and series:
        total_points = max(len(s.data) for s in series) if series else 0

    # 11. anomaly_nodes 조립 (항상 월 단위)
    anomaly_nodes: list[AnomalyNode] = []
    for ar in anomaly_rows:
        try:
            anomaly_nodes.append(
                AnomalyNode(
                    anomaly_id=ar.id,
                    segment_id=ar.segment_id,
                    period=_safe_period(ar.period, "anomaly_results", "period"),
                    primary_pattern=ar.primary_pattern,
                    pattern_types=ar.pattern_types or [],
                    confidence_grade=ar.confidence_grade,
                    transmission_rate=_safe_float(ar.transmission_rate, "anomaly_results", "transmission_rate"),
                    is_new=bool(ar.is_new),
                )
            )
        except (ParseError, Exception) as e:
            if isinstance(e, ParseError | APIError):
                raise
            raise APIError(
                "API-INT-001",
                "이상 노드 직렬화 오류",
                context={"anomaly_id": ar.id},
                http_status=500,
                public_code="INTERNAL_ERROR",
            ) from e

    return StreamResponse(
        commodity_id=commodity_id,
        requested_from=requested_from.strftime("%Y-%m"),
        requested_to=requested_to.strftime("%Y-%m"),
        actual_from=actual_from.strftime("%Y-%m"),
        actual_to=actual_to.strftime("%Y-%m"),
        granularity=granularity,
        total_points=total_points,
        series=series,
        anomaly_nodes=anomaly_nodes,
    )


# ── /stream/minimap ────────────────────────────────────────────────────────────

async def get_stream_minimap(
    db: AsyncSession,
    commodity_id: str,
    analysis_start: date,
    analysis_end: date,
    commodity_segments: list[str],
    segments_str: str | None,
) -> StreamMinimapResponse:
    """스트림 미니맵 — 전체 기간 yearly 고정 + mv_anomaly_density_yearly (feature_spec_API-STR_v5 §1.2)."""
    # 구간 필터 파싱 및 검증 (API-SEG-001)
    segments_filter: list[str] = (
        [s.strip() for s in segments_str.split(",") if s.strip()]
        if segments_str
        else list(commodity_segments)
    )
    for seg in segments_filter:
        if seg not in commodity_segments:
            raise APIError(
                "API-SEG-001",
                "해당 품목에 존재하지 않는 구간입니다.",
                context={
                    "commodity_id": commodity_id,
                    "requested_segment": seg,
                    "available_segments": commodity_segments,
                },
                http_status=400,
                public_code="INVALID_SEGMENT",
            )

    # 전체 기간, granularity=yearly 고정
    actual_from = analysis_start
    actual_to = analysis_end

    # stat_timeseries 전체 기간 조회 (yearly 집계용)
    try:
        ts_result = await db.execute(
            select(StatTimeseries)
            .where(
                and_(
                    StatTimeseries.commodity_id == commodity_id,
                    StatTimeseries.segment_id.in_(segments_filter),
                )
            )
            .order_by(StatTimeseries.segment_id, StatTimeseries.period)
        )
        ts_rows = ts_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "스트림 미니맵 시계열 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # mv_anomaly_density_yearly 조회
    try:
        density_result = await db.execute(
            select(MvAnomalyDensityYearly)
            .where(
                and_(
                    MvAnomalyDensityYearly.commodity_id == commodity_id,
                    MvAnomalyDensityYearly.segment_id.in_(segments_filter),
                )
            )
            .order_by(MvAnomalyDensityYearly.year)
        )
        density_rows = density_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "이상 밀도 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 이상 노드 인덱스 (미니맵용 — 이상 정보는 anomaly_density로 대체)
    seg_monthly: dict[str, list[dict]] = defaultdict(list)
    for row in ts_rows:
        seg_monthly[row.segment_id].append({
            "period": row.period,
            "transmission_rate": _safe_float(row.transmission_rate, "stat_timeseries", "transmission_rate"),
            "upstream_pct": _safe_float(row.upstream_pct, "stat_timeseries", "upstream_pct"),
            "downstream_pct": _safe_float(row.downstream_pct, "stat_timeseries", "downstream_pct"),
            "in_warmup_period": bool(row.in_warmup_period),
            "anomaly_ids": [],  # 미니맵 series 데이터에는 anomaly_ids 미포함
        })

    series: list[StreamSeries] = []
    total_points = 0
    for seg_id in segments_filter:
        monthly = seg_monthly.get(seg_id, [])
        aggregated = aggregate_by_granularity(
            monthly, "yearly",
            avg_fields=("transmission_rate", "upstream_pct", "downstream_pct"),
            any_fields=("in_warmup_period",),
            concat_fields=("anomaly_ids",),
        )
        points = [
            StreamDataPoint(
                period=_safe_period(p["period"], "stat_timeseries", "period"),
                transmission_rate=p["transmission_rate"],
                upstream_pct=p["upstream_pct"],
                downstream_pct=p["downstream_pct"],
                in_warmup_period=p["in_warmup_period"],
                has_anomaly=False,
                anomaly_ids=[],
            )
            for p in aggregated
        ]
        series.append(StreamSeries(segment_id=seg_id, data=points))
        if not total_points and points:
            total_points = len(points)
    if total_points == 0 and series:
        total_points = max(len(s.data) for s in series) if series else 0

    # 연도별 밀도 집계 (구간 합산)
    anomaly_density = build_anomaly_density(density_rows)

    return StreamMinimapResponse(
        commodity_id=commodity_id,
        requested_from=actual_from.strftime("%Y-%m"),
        requested_to=actual_to.strftime("%Y-%m"),
        actual_from=actual_from.strftime("%Y-%m"),
        actual_to=actual_to.strftime("%Y-%m"),
        granularity="yearly",
        total_points=total_points,
        series=series,
        anomaly_nodes=[],
        anomaly_density=anomaly_density,
    )
