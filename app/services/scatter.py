"""산점도 비즈니스 로직 (feature_spec_API-STR_v5 §1.2).

엔드포인트: GET /commodities/{id}/scatter
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError
from app.db.models.anomaly import AnomalyResult
from app.db.models.commodity import Segment
from app.db.models.reference import Baseline
from app.db.models.timeseries import StatTimeseries
from app.schemas.timeseries import (
    ScatterBaseline,
    ScatterPoint,
    ScatterResponse,
)
from app.services.stream import _clamp_range, _parse_yyyymm, _safe_float, _safe_period


# ── /scatter ──────────────────────────────────────────────────────────────────

async def get_scatter(
    db: AsyncSession,
    commodity_id: str,
    segment_id: str,
    analysis_start: date,
    analysis_end: date,
    commodity_segments: list[str],
    from_str: str | None,
    to_str: str | None,
    until_str: str | None,
    grade_str: str = "high,medium",
) -> ScatterResponse:
    """전달 구조 산점도 반환 (feature_spec_API-STR_v5 §1.2).

    - segment 검증 (API-SEG-001)
    - until 검증 (API-STR-005): analysis_start ≤ until ≤ analysis_end
    - warmup 전용 체크 (API-STR-001)
    - baselines: subperiod_id IS NULL (D-15 전체 기간 기준선)
    - 항상 월 단위 (granularity 없음)
    """
    # 1. segment 검증 (API-SEG-001)
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

    # 2. 날짜 파싱 및 클램핑
    requested_from = _parse_yyyymm(from_str, "from") if from_str else analysis_start
    requested_to = _parse_yyyymm(to_str, "to") if to_str else analysis_end
    actual_from, actual_to = _clamp_range(
        requested_from, requested_to, analysis_start, analysis_end, commodity_id
    )

    # 3. until 검증 (API-STR-005)
    until: date | None = None
    if until_str:
        until = _parse_yyyymm(until_str, "until")
        if until < analysis_start or until > analysis_end:
            raise APIError(
                "API-STR-005",
                "until이 분석 가용 범위를 벗어났습니다.",
                context={
                    "until": until_str,
                    "analysis_start": str(analysis_start),
                    "analysis_end": str(analysis_end),
                    "commodity_id": commodity_id,
                },
                http_status=400,
                public_code="INVALID_DATE_RANGE",
            )

    # 4. stat_timeseries 조회 (upstream_pct, downstream_pct)
    try:
        ts_result = await db.execute(
            select(StatTimeseries)
            .where(
                and_(
                    StatTimeseries.commodity_id == commodity_id,
                    StatTimeseries.segment_id == segment_id,
                    StatTimeseries.period >= actual_from,
                    StatTimeseries.period <= actual_to,
                )
            )
            .order_by(StatTimeseries.period)
        )
        ts_rows = ts_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "산점도 시계열 조회 중 DB 오류",
            context={"commodity_id": commodity_id, "segment_id": segment_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 5. warmup 전용 체크 (API-STR-001)
    if ts_rows and all(r.in_warmup_period for r in ts_rows):
        raise APIError(
            "API-STR-001",
            "요청한 기간은 분석 기준 분포 축적 기간입니다.",
            context={
                "commodity_id": commodity_id,
                "segment_id": segment_id,
                "from": str(actual_from),
                "to": str(actual_to),
            },
            http_status=404,
            public_code="WARMUP_PERIOD_ONLY",
        )

    # 6. anomaly_results 조회 (scatter용 — 색상/마커 목적, grade 필터 적용)
    grade_filter = [g.strip() for g in grade_str.split(",") if g.strip()]
    try:
        anomaly_result = await db.execute(
            select(AnomalyResult)
            .where(
                and_(
                    AnomalyResult.commodity_id == commodity_id,
                    AnomalyResult.segment_id == segment_id,
                    AnomalyResult.confidence_grade.in_(grade_filter),
                    AnomalyResult.period >= actual_from,
                    AnomalyResult.period <= actual_to,
                )
            )
        )
        anomaly_rows = anomaly_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "산점도 이상 조회 중 DB 오류",
            context={"commodity_id": commodity_id, "segment_id": segment_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # (period, segment_id) → anomaly row 인덱스
    anomaly_map: dict[date, AnomalyResult] = {ar.period: ar for ar in anomaly_rows}

    # 7. baselines 조회 (subperiod_id IS NULL — D-15 전체 기간 기준선)
    try:
        baseline_result = await db.execute(
            select(Baseline)
            .where(
                and_(
                    Baseline.commodity_id == commodity_id,
                    Baseline.segment_id == segment_id,
                    Baseline.subperiod_id.is_(None),
                )
            )
            .limit(1)
        )
        baseline_row = baseline_result.scalar_one_or_none()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "기준선 조회 중 DB 오류",
            context={"commodity_id": commodity_id, "segment_id": segment_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 8. segments 조회 (upstream_label, downstream_label)
    try:
        seg_result = await db.execute(
            select(Segment).where(Segment.segment_id == segment_id)
        )
        seg_row = seg_result.scalar_one_or_none()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "세그먼트 레이블 조회 중 DB 오류",
            context={"segment_id": segment_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    upstream_label = seg_row.upstream_label if seg_row else segment_id
    downstream_label = seg_row.downstream_label if seg_row else segment_id

    # 9. 산점도 포인트 조립
    points: list[ScatterPoint] = []
    for row in ts_rows:
        ar = anomaly_map.get(row.period)
        points.append(
            ScatterPoint(
                period=_safe_period(row.period, "stat_timeseries", "period"),
                upstream_pct=_safe_float(row.upstream_pct, "stat_timeseries", "upstream_pct"),
                downstream_pct=_safe_float(row.downstream_pct, "stat_timeseries", "downstream_pct"),
                is_anomaly=ar is not None,
                anomaly_id=ar.id if ar else None,
                confidence_grade=ar.confidence_grade if ar else None,
                primary_pattern=ar.primary_pattern if ar else None,
            )
        )

    # 10. baseline DTO
    baseline = ScatterBaseline(
        transmission_elasticity=_safe_float(
            baseline_row.transmission_elasticity, "baselines", "transmission_elasticity"
        ) if baseline_row else None,
        normal_transmission_lag=int(baseline_row.normal_transmission_lag) if baseline_row else None,
    )

    return ScatterResponse(
        commodity_id=commodity_id,
        segment_id=segment_id,
        upstream_label=upstream_label,
        downstream_label=downstream_label,
        until=until.strftime("%Y-%m") if until else None,
        baseline=baseline,
        points=points,
        requested_from=requested_from.strftime("%Y-%m"),
        requested_to=requested_to.strftime("%Y-%m"),
        actual_from=actual_from.strftime("%Y-%m"),
        actual_to=actual_to.strftime("%Y-%m"),
        granularity="monthly",
        total_points=len(points),
    )
