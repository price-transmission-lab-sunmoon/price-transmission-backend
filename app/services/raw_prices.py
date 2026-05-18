"""원시 시계열·미니맵 비즈니스 로직 (feature_spec_API-STR_v5 §1.2).

엔드포인트: GET /commodities/{id}/raw-prices
            GET /commodities/{id}/raw-prices/minimap
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError
from app.db.models.anomaly import AnomalyResult
from app.db.models.timeseries import MvAnomalyDensityYearly, RawPrice, StatTimeseries
from app.schemas.timeseries import (
    AnomalyDensityPoint,
    RawPriceAnomalyNode,
    RawPriceDataPoint,
    RawPriceSeries,
    RawPricesMinimapResponse,
    RawPricesResponse,
    StreamDataPoint,
    TransmissionOverlaySeries,
)
from app.services.stream import (
    _aggregate_monthly_points,
    _clamp_range,
    _parse_yyyymm,
    _safe_float,
    _safe_period,
)

# ── 소스 메타데이터 ─────────────────────────────────────────────────────────────

# DB 컬럼명 → (label_kr, color_hint, index_column)
_SOURCE_META: dict[str, tuple[str, str, str]] = {
    "intl_price_krw":  ("국제가 (원화 환산)",        "purple", "intl_price_krw_idx"),
    "import_price_usd": ("수입단가",                 "orange", "import_price_idx"),
    "ppi":             ("생산자물가지수 (PPI)",        "green",  "ppi_idx"),
    "cpi":             ("소비자물가지수 (CPI)",        "red",    "cpi_idx"),
    "wholesale_price": ("도매가격",                  "blue",   "wholesale_price_idx"),
}

# 레이아웃별 소스 (api_spec_vN §D-12)
_LAYOUT_SOURCES_4SEG: dict[int, list[str]] = {
    1: ["intl_price_krw", "import_price_usd", "ppi", "wholesale_price", "cpi"],
    2: ["intl_price_krw", "import_price_usd"],
    3: ["import_price_usd", "ppi"],
    4: ["ppi", "wholesale_price"],
    5: ["wholesale_price", "cpi"],
    6: ["intl_price_krw", "import_price_usd", "ppi", "wholesale_price", "cpi"],
}

_LAYOUT_SOURCES_3SEG: dict[int, list[str]] = {
    1: ["intl_price_krw", "import_price_usd", "ppi", "cpi"],
    2: ["intl_price_krw", "import_price_usd"],
    3: ["import_price_usd", "ppi"],
    # 4: 에러 (API-LAY-002)
    5: ["ppi", "cpi"],  # wholesale→ppi 자동 폴백 (D-12)
    6: ["intl_price_krw", "import_price_usd", "ppi", "cpi"],
}


def _resolve_sources(layout: int, route_type: str, commodity_id: str) -> list[str]:
    """레이아웃 + route_type → DB 컬럼 목록 반환.

    3구간 품목 레이아웃 4 → API-LAY-002.
    3구간 품목 레이아웃 5 → PPI-CPI 자동 폴백 (에러 없음, D-12).
    """
    if layout < 1 or layout > 6:
        raise APIError(
            "API-LAY-001",
            "layout은 1~6 사이여야 합니다.",
            context={"layout": layout, "commodity_id": commodity_id},
            http_status=400,
            public_code="INVALID_LAYOUT",
        )
    is_3seg = (route_type == "3seg")
    if is_3seg and layout == 4:
        raise APIError(
            "API-LAY-002",
            "3구간 품목에는 도매가격(레이아웃 4)이 제공되지 않습니다.",
            context={"layout": layout, "commodity_id": commodity_id, "route_type": route_type},
            http_status=400,
            public_code="WHOLESALE_NOT_AVAILABLE",
        )
    if is_3seg:
        return _LAYOUT_SOURCES_3SEG[layout]
    return _LAYOUT_SOURCES_4SEG[layout]


def _aggregate_raw_monthly(
    monthly: list[dict],
    granularity: Literal["monthly", "quarterly", "yearly"],
) -> list[dict]:
    """raw_prices 월 포인트 → granularity 집계.

    각 dict: {period: date, value, index_2020, has_anomaly: bool, anomaly_ids: list}
    """
    if granularity == "monthly":
        return monthly

    from app.services.stream import _quarter_key, _quarter_last_month

    if granularity == "quarterly":
        key_fn = _quarter_key
        period_fn = lambda k: _quarter_last_month(k[0], k[1])
    else:  # yearly
        key_fn = lambda p: p["period"].year
        period_fn = lambda k: date(k, 12, 1)

    groups: dict = defaultdict(list)
    for p in monthly:
        groups[key_fn(p)].append(p)

    result: list[dict] = []
    for k in sorted(groups):
        grp = groups[k]

        def avg(field: str) -> float | None:
            vals = [p[field] for p in grp if p[field] is not None]
            return sum(vals) / len(vals) if vals else None

        all_ids = [aid for p in grp for aid in p["anomaly_ids"]]
        result.append({
            "period": period_fn(k),
            "value": avg("value"),
            "index_2020": avg("index_2020"),
            "has_anomaly": any(p["has_anomaly"] for p in grp),
            "anomaly_ids": all_ids,
        })
    return result


# ── /raw-prices ────────────────────────────────────────────────────────────────

async def get_raw_prices(
    db: AsyncSession,
    commodity_id: str,
    route_type: str,
    commodity_segments: list[str],
    analysis_start: date,
    analysis_end: date,
    layout: int,
    from_str: str | None,
    to_str: str | None,
    granularity: str,
) -> RawPricesResponse:
    """원시 시계열 반환 (feature_spec_API-STR_v5 §1.2)."""
    # 1. granularity 검증 (API-STR-004)
    if granularity not in ("monthly", "quarterly", "yearly"):
        raise APIError(
            "API-STR-004",
            "granularity는 monthly / quarterly / yearly 중 하나여야 합니다.",
            context={"granularity": granularity},
            http_status=400,
            public_code="INVALID_GRANULARITY",
        )

    # 2. 레이아웃 → 소스 결정 (API-LAY-001, API-LAY-002)
    sources = _resolve_sources(layout, route_type, commodity_id)

    # 3. 날짜 파싱 및 클램핑
    requested_from = _parse_yyyymm(from_str, "from") if from_str else analysis_start
    requested_to = _parse_yyyymm(to_str, "to") if to_str else analysis_end
    actual_from, actual_to = _clamp_range(
        requested_from, requested_to, analysis_start, analysis_end, commodity_id
    )

    # 4. raw_prices 조회
    try:
        rp_result = await db.execute(
            select(RawPrice)
            .where(
                and_(
                    RawPrice.commodity_id == commodity_id,
                    RawPrice.period >= actual_from,
                    RawPrice.period <= actual_to,
                )
            )
            .order_by(RawPrice.period)
        )
        rp_rows = rp_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "원시 시계열 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 5. warmup 전용 체크 (API-STR-001) — stat_timeseries로 warmup 여부 판단
    try:
        wm_result = await db.execute(
            select(StatTimeseries.in_warmup_period)
            .where(
                and_(
                    StatTimeseries.commodity_id == commodity_id,
                    StatTimeseries.period >= actual_from,
                    StatTimeseries.period <= actual_to,
                )
            )
        )
        warmup_flags = [row for row in wm_result.scalars().all()]
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "warmup 기간 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    if warmup_flags and all(warmup_flags):
        raise APIError(
            "API-STR-001",
            "요청한 기간은 분석 기준 분포 축적 기간입니다.",
            context={"commodity_id": commodity_id, "from": str(actual_from), "to": str(actual_to)},
            http_status=404,
            public_code="WARMUP_PERIOD_ONLY",
        )

    # 6. anomaly_results 조회 (모든 구간)
    try:
        anomaly_result = await db.execute(
            select(AnomalyResult)
            .where(
                and_(
                    AnomalyResult.commodity_id == commodity_id,
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
            "이상 노드 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # period → anomaly_id 목록 (raw_prices는 commodity 단위이므로 구간 무관 합산)
    period_anomaly_ids: dict[date, list[int]] = defaultdict(list)
    for ar in anomaly_rows:
        period_anomaly_ids[ar.period].append(ar.id)

    # 7. 소스별 월 포인트 조립 → granularity 집계 → RawPriceSeries
    series: list[RawPriceSeries] = []
    total_points = 0

    for src in sources:
        meta = _SOURCE_META[src]
        label_kr, color_hint, idx_col = meta

        monthly: list[dict] = []
        for row in rp_rows:
            raw_val = getattr(row, src, None)
            idx_val = getattr(row, idx_col, None)
            ids = period_anomaly_ids.get(row.period, [])
            monthly.append({
                "period": row.period,
                "value": _safe_float(raw_val, "raw_prices", src),
                "index_2020": _safe_float(idx_val, "raw_prices", idx_col),
                "has_anomaly": bool(ids),
                "anomaly_ids": ids,
            })

        aggregated = _aggregate_raw_monthly(monthly, granularity)
        points = [
            RawPriceDataPoint(
                period=_safe_period(p["period"], "raw_prices", "period"),
                value=p["value"],
                index_2020=p["index_2020"],
                has_anomaly=p["has_anomaly"],
                anomaly_ids=p["anomaly_ids"],
            )
            for p in aggregated
        ]
        series.append(RawPriceSeries(source=src, label_kr=label_kr, color_hint=color_hint, data=points))
        if points and not total_points:
            total_points = len(points)

    if total_points == 0 and series:
        total_points = max(len(s.data) for s in series) if series else 0

    # 8. transmission_overlay — 레이아웃 2~6에서만 포함 (api_spec_vN §raw-prices)
    transmission_overlay: list[TransmissionOverlaySeries] = []
    if layout != 1:
        try:
            ts_result = await db.execute(
                select(StatTimeseries)
                .where(
                    and_(
                        StatTimeseries.commodity_id == commodity_id,
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
                "전이율 오버레이 조회 중 DB 오류",
                context={"commodity_id": commodity_id},
                http_status=500,
                public_code="INTERNAL_ERROR",
            ) from e

        seg_ts: dict[str, list[dict]] = defaultdict(list)
        seg_anomaly: dict[tuple[str, date], list[int]] = defaultdict(list)
        for ar in anomaly_rows:
            seg_anomaly[(ar.segment_id, ar.period)].append(ar.id)

        for row in ts_rows:
            ids = seg_anomaly.get((row.segment_id, row.period), [])
            seg_ts[row.segment_id].append({
                "period": row.period,
                "transmission_rate": _safe_float(row.transmission_rate, "stat_timeseries", "transmission_rate"),
                "upstream_pct": _safe_float(row.upstream_pct, "stat_timeseries", "upstream_pct"),
                "downstream_pct": _safe_float(row.downstream_pct, "stat_timeseries", "downstream_pct"),
                "in_warmup_period": bool(row.in_warmup_period),
                "anomaly_ids": ids,
            })

        for seg_id in commodity_segments:
            monthly_seg = seg_ts.get(seg_id, [])
            aggregated_seg = _aggregate_monthly_points(monthly_seg, granularity)
            overlay_points = [
                StreamDataPoint(
                    period=_safe_period(p["period"], "stat_timeseries", "period"),
                    transmission_rate=p["transmission_rate"],
                    upstream_pct=p["upstream_pct"],
                    downstream_pct=p["downstream_pct"],
                    in_warmup_period=p["in_warmup_period"],
                    has_anomaly=bool(p["anomaly_ids"]),
                    anomaly_ids=p["anomaly_ids"],
                )
                for p in aggregated_seg
            ]
            transmission_overlay.append(
                TransmissionOverlaySeries(segment_id=seg_id, data=overlay_points)
            )

    # 9. anomaly_nodes 조립 (항상 월 단위)
    anomaly_nodes: list[RawPriceAnomalyNode] = [
        RawPriceAnomalyNode(
            anomaly_id=ar.id,
            segment_id=ar.segment_id,
            period=_safe_period(ar.period, "anomaly_results", "period"),
            confidence_grade=ar.confidence_grade,
            primary_pattern=ar.primary_pattern,
            is_new=bool(ar.is_new),
        )
        for ar in anomaly_rows
    ]

    return RawPricesResponse(
        commodity_id=commodity_id,
        layout=layout,
        requested_from=requested_from.strftime("%Y-%m"),
        requested_to=requested_to.strftime("%Y-%m"),
        actual_from=actual_from.strftime("%Y-%m"),
        actual_to=actual_to.strftime("%Y-%m"),
        granularity=granularity,
        total_points=total_points,
        series=series,
        transmission_overlay=transmission_overlay,
        anomaly_nodes=anomaly_nodes,
    )


# ── /raw-prices/minimap ───────────────────────────────────────────────────────

async def get_raw_prices_minimap(
    db: AsyncSession,
    commodity_id: str,
    route_type: str,
    commodity_segments: list[str],
    analysis_start: date,
    analysis_end: date,
    layout: int,
) -> RawPricesMinimapResponse:
    """원시 시계열 미니맵 — 전체 기간 yearly 고정 + anomaly_density (feature_spec_API-STR_v5 §1.2)."""
    # 1. 레이아웃 → 소스 결정 (API-LAY-001, API-LAY-002)
    sources = _resolve_sources(layout, route_type, commodity_id)

    actual_from = analysis_start
    actual_to = analysis_end

    # 2. raw_prices 전체 기간 조회
    try:
        rp_result = await db.execute(
            select(RawPrice)
            .where(RawPrice.commodity_id == commodity_id)
            .order_by(RawPrice.period)
        )
        rp_rows = rp_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "원시 시계열 미니맵 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    # 3. mv_anomaly_density_yearly 조회
    try:
        density_result = await db.execute(
            select(MvAnomalyDensityYearly)
            .where(MvAnomalyDensityYearly.commodity_id == commodity_id)
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

    # 4. anomaly_results 조회 (anomaly_nodes용)
    try:
        anomaly_result = await db.execute(
            select(AnomalyResult)
            .where(AnomalyResult.commodity_id == commodity_id)
            .order_by(AnomalyResult.period)
        )
        anomaly_rows = anomaly_result.scalars().all()
    except Exception as e:
        raise APIError(
            "API-INT-001",
            "이상 노드 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e

    period_anomaly_ids: dict[date, list[int]] = defaultdict(list)
    for ar in anomaly_rows:
        period_anomaly_ids[ar.period].append(ar.id)

    # 5. 소스별 yearly 집계
    series: list[RawPriceSeries] = []
    total_points = 0

    for src in sources:
        meta = _SOURCE_META[src]
        label_kr, color_hint, idx_col = meta

        monthly: list[dict] = []
        for row in rp_rows:
            ids = period_anomaly_ids.get(row.period, [])
            raw_val = getattr(row, src, None)
            idx_val = getattr(row, idx_col, None)
            monthly.append({
                "period": row.period,
                "value": _safe_float(raw_val, "raw_prices", src),
                "index_2020": _safe_float(idx_val, "raw_prices", idx_col),
                "has_anomaly": bool(ids),
                "anomaly_ids": ids,
            })

        aggregated = _aggregate_raw_monthly(monthly, "yearly")
        points = [
            RawPriceDataPoint(
                period=_safe_period(p["period"], "raw_prices", "period"),
                value=p["value"],
                index_2020=p["index_2020"],
                has_anomaly=p["has_anomaly"],
                anomaly_ids=p["anomaly_ids"],
            )
            for p in aggregated
        ]
        series.append(RawPriceSeries(source=src, label_kr=label_kr, color_hint=color_hint, data=points))
        if points and not total_points:
            total_points = len(points)

    if total_points == 0 and series:
        total_points = max(len(s.data) for s in series) if series else 0

    # 6. transmission_overlay — 미니맵도 layout 2~6이면 포함
    transmission_overlay: list[TransmissionOverlaySeries] = []
    if layout != 1:
        try:
            ts_result = await db.execute(
                select(StatTimeseries)
                .where(StatTimeseries.commodity_id == commodity_id)
                .order_by(StatTimeseries.segment_id, StatTimeseries.period)
            )
            ts_rows = ts_result.scalars().all()
        except Exception as e:
            raise APIError(
                "API-INT-001",
                "전이율 오버레이 조회 중 DB 오류",
                context={"commodity_id": commodity_id},
                http_status=500,
                public_code="INTERNAL_ERROR",
            ) from e

        seg_ts: dict[str, list[dict]] = defaultdict(list)
        seg_anomaly: dict[tuple[str, date], list[int]] = defaultdict(list)
        for ar in anomaly_rows:
            seg_anomaly[(ar.segment_id, ar.period)].append(ar.id)

        for row in ts_rows:
            ids = seg_anomaly.get((row.segment_id, row.period), [])
            seg_ts[row.segment_id].append({
                "period": row.period,
                "transmission_rate": _safe_float(row.transmission_rate, "stat_timeseries", "transmission_rate"),
                "upstream_pct": _safe_float(row.upstream_pct, "stat_timeseries", "upstream_pct"),
                "downstream_pct": _safe_float(row.downstream_pct, "stat_timeseries", "downstream_pct"),
                "in_warmup_period": bool(row.in_warmup_period),
                "anomaly_ids": ids,
            })

        for seg_id in commodity_segments:
            monthly_seg = seg_ts.get(seg_id, [])
            aggregated_seg = _aggregate_monthly_points(monthly_seg, "yearly")
            overlay_points = [
                StreamDataPoint(
                    period=_safe_period(p["period"], "stat_timeseries", "period"),
                    transmission_rate=p["transmission_rate"],
                    upstream_pct=p["upstream_pct"],
                    downstream_pct=p["downstream_pct"],
                    in_warmup_period=p["in_warmup_period"],
                    has_anomaly=bool(p["anomaly_ids"]),
                    anomaly_ids=p["anomaly_ids"],
                )
                for p in aggregated_seg
            ]
            transmission_overlay.append(
                TransmissionOverlaySeries(segment_id=seg_id, data=overlay_points)
            )

    # 7. anomaly_nodes (항상 월 단위)
    anomaly_nodes: list[RawPriceAnomalyNode] = [
        RawPriceAnomalyNode(
            anomaly_id=ar.id,
            segment_id=ar.segment_id,
            period=_safe_period(ar.period, "anomaly_results", "period"),
            confidence_grade=ar.confidence_grade,
            primary_pattern=ar.primary_pattern,
            is_new=bool(ar.is_new),
        )
        for ar in anomaly_rows
    ]

    # 8. 연도별 밀도 집계 (구간 합산)
    year_density: dict[int, dict] = {}
    for dr in density_rows:
        y = int(dr.year)
        if y not in year_density:
            year_density[y] = {"high_count": 0, "medium_count": 0, "reference_count": 0}
        year_density[y]["high_count"] += int(dr.high_count or 0)
        year_density[y]["medium_count"] += int(dr.medium_count or 0)
        year_density[y]["reference_count"] += int(dr.reference_count or 0)

    anomaly_density = [
        AnomalyDensityPoint(
            period=str(y),
            high_count=v["high_count"],
            medium_count=v["medium_count"],
            reference_count=v["reference_count"],
        )
        for y, v in sorted(year_density.items())
    ]

    return RawPricesMinimapResponse(
        commodity_id=commodity_id,
        layout=layout,
        requested_from=actual_from.strftime("%Y-%m"),
        requested_to=actual_to.strftime("%Y-%m"),
        actual_from=actual_from.strftime("%Y-%m"),
        actual_to=actual_to.strftime("%Y-%m"),
        granularity="yearly",
        total_points=total_points,
        series=series,
        transmission_overlay=transmission_overlay,
        anomaly_nodes=anomaly_nodes,
        anomaly_density=anomaly_density,
    )
