"""패널 엔드포인트 서비스 — /detail, /stat-series, /stat-snapshot, /irf, /ml-map.

api_spec_vN §패널 엔드포인트, feature_spec_API-PANEL 기준.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import APIError
from app.db.models.anomaly import (
    AnomalyResult,
    AsymmetryResult,
    Baseline,
    Breakpoint,
    CointegrationResult,
    IRFData,
    MLProjection,
    MLScore,
    Subperiod,
)
from app.db.models.commodity import Commodity, Segment
from app.db.models.timeseries import StatTimeseries
from app.schemas.anomaly import (
    AnomalyDetailResponse,
    JudgmentStep,
    MLSummary,
    StatMetrics,
)
from app.schemas.panel import (
    IRFCurve,
    IRFDataPoint,
    IRFResponse,
    MLMapResponse,
    StatSnapshotAsymmetryResponse,
    StatSnapshotIQRResponse,
)
from app.schemas.timeseries import StatSeriesPoint, StatSeriesResponse


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _period_str(d: date | None) -> str:
    if d is None:
        return ""
    return d.strftime("%Y-%m")


def _parse_yyyymm(value: str, field: str) -> date:
    m = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not m:
        raise APIError(
            "API-MET-001",
            f"날짜 형식이 올바르지 않습니다: {value!r}",
            context={"field": field, "value": value},
            http_status=400,
            public_code="INVALID_DATE_RANGE",
        )
    y, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12):
        raise APIError(
            "API-MET-001",
            f"날짜 형식이 올바르지 않습니다: {value!r}",
            context={"field": field, "value": value},
            http_status=400,
            public_code="INVALID_DATE_RANGE",
        )
    return date(y, mo, 1)


async def _get_anomaly_or_404(db: AsyncSession, anomaly_id: int) -> AnomalyResult:
    """anomaly_results 단건 조회. 미존재 시 API-ANO-001."""
    ar = (await db.execute(
        select(AnomalyResult).where(AnomalyResult.id == anomaly_id)
    )).scalar_one_or_none()
    if ar is None:
        raise APIError(
            "API-ANO-001",
            "해당 이상 항목이 존재하지 않습니다.",
            context={"anomaly_id": anomaly_id},
            http_status=404,
            public_code="ANOMALY_NOT_FOUND",
        )
    return ar


async def _get_commodity_name(db: AsyncSession, cid: str) -> str:
    c = (await db.execute(
        select(Commodity).where(Commodity.commodity_id == cid)
    )).scalar_one_or_none()
    return c.name_kr if c else cid


async def _get_segment_label(db: AsyncSession, seg_id: str) -> str:
    s = (await db.execute(
        select(Segment).where(Segment.segment_id == seg_id)
    )).scalar_one_or_none()
    return s.label_kr if s else seg_id


async def _get_stat_at(
    db: AsyncSession, cid: str, seg: str, period: date
) -> StatTimeseries | None:
    return (await db.execute(
        select(StatTimeseries).where(and_(
            StatTimeseries.commodity_id == cid,
            StatTimeseries.segment_id == seg,
            StatTimeseries.period == period,
        ))
    )).scalar_one_or_none()


# ── /detail ──────────────────────────────────────────────────────────────────

async def get_detail(anomaly_id: int, db: AsyncSession) -> AnomalyDetailResponse:
    """이상 항목 상세 — anomaly_results + 관련 테이블 통합."""
    ar = await _get_anomaly_or_404(db, anomaly_id)

    stat = await _get_stat_at(db, ar.commodity_id, ar.segment_id, ar.period)
    baseline = (await db.execute(
        select(Baseline).where(and_(
            Baseline.commodity_id == ar.commodity_id,
            Baseline.segment_id == ar.segment_id,
            Baseline.subperiod_id.is_(None),
        ))
    )).scalar_one_or_none()
    coint = (await db.execute(
        select(CointegrationResult).where(and_(
            CointegrationResult.commodity_id == ar.commodity_id,
            CointegrationResult.segment_id == ar.segment_id,
        ))
    )).scalar_one_or_none()
    asym = (await db.execute(
        select(AsymmetryResult).where(and_(
            AsymmetryResult.commodity_id == ar.commodity_id,
            AsymmetryResult.segment_id == ar.segment_id,
        ))
    )).scalar_one_or_none()
    bp = (await db.execute(
        select(Breakpoint).where(and_(
            Breakpoint.commodity_id == ar.commodity_id,
            Breakpoint.segment_id == ar.segment_id,
        ))
    )).scalar_one_or_none()
    ml = (await db.execute(
        select(MLScore).where(and_(
            MLScore.commodity_id == ar.commodity_id,
            MLScore.segment_id == ar.segment_id,
            MLScore.period == ar.period,
        ))
    )).scalar_one_or_none()

    commodity_name = await _get_commodity_name(db, ar.commodity_id)
    segment_label = await _get_segment_label(db, ar.segment_id)

    stat_metrics = StatMetrics(
        transmission_rate=_f(ar.transmission_rate) if ar.transmission_rate is not None else _f(stat.transmission_rate if stat else None),
        rolling_mean=_f(stat.rolling_mean) if stat else None,
        zscore=_f(ar.zscore_value),
        zscore_warning=bool(ar.zscore_warning),
        zscore_alert=bool(ar.zscore_alert),
        zscore_threshold_warning=settings.zscore_warning,
        zscore_threshold_alert=settings.zscore_alert,
        q1=_f(stat.q1) if stat else None,
        q3=_f(stat.q3) if stat else None,
        iqr_lower=_f(stat.iqr_lower) if stat else None,
        iqr_upper=_f(stat.iqr_upper) if stat else None,
        iqr_outlier=bool(ar.iqr_outlier),
        over_transmission=bool(ar.over_transmission),
        under_transmission=bool(ar.under_transmission),
        normal_lag=baseline.normal_transmission_lag if baseline else (ar.normal_lag if ar.normal_lag is not None else None),
        actual_lag=ar.actual_lag,
        direction_reversal=bool(ar.direction_reversal),
        lag_deviation=bool(ar.lag_deviation),
        pattern1_flag_type=ar.pattern1_flag_type if ar.pattern1_flag_type in ("direction_reversal", "lag_deviation", "both") else None,
        ect_or_spread=_f(stat.ect_or_spread) if stat else None,
        ect_type=stat.ect_type if stat and stat.ect_type in ("ECT", "log_spread") else None,
        spread_n3=_f(ar.spread_n3_value),
        alpha_plus=_f(asym.alpha_plus) if asym else None,
        alpha_minus=_f(asym.alpha_minus) if asym else None,
        wald_pvalue=_f(asym.wald_pvalue) if asym else None,
        asymmetry_significant=bool(asym.asymmetry_significant) if asym else None,
        rocket_feather_direction=asym.rocket_feather_direction if asym else None,
        model_type=(baseline.model_type if baseline and baseline.model_type in ("VAR", "VECM") else None),
        cointegrated=bool(coint.cointegrated) if coint and coint.cointegrated is not None else None,
        subperiod_index=None,  # 추후 subperiod join 필요
        bp_dates=[_period_str(d) for d in (bp.bp_dates or [])] if bp else [],
    )

    ml_summary = MLSummary(
        ml_vote=int(ar.ml_vote or 0),
        ml_detected=bool(ar.ml_detected),
        if_anomaly=bool(ml.if_anomaly) if ml and ml.if_anomaly is not None else ar.if_anomaly,
        if_score=_f(ml.if_score) if ml else None,
        if_percentile=_f(ml.if_percentile) if ml else None,
        lof_anomaly=bool(ml.lof_anomaly) if ml and ml.lof_anomaly is not None else ar.lof_anomaly,
        lof_score=_f(ml.lof_score) if ml else None,
        lof_percentile=_f(ml.lof_percentile) if ml else None,
        svm_anomaly=bool(ml.svm_anomaly) if ml and ml.svm_anomaly is not None else ar.svm_anomaly,
        svm_score=_f(ml.svm_score) if ml else None,
        svm_percentile=_f(ml.svm_percentile) if ml else None,
    )

    # judgment_path — 5단계 판정 흐름 요약
    judgment_path = _build_judgment_path(ar, stat_metrics)

    return AnomalyDetailResponse(
        anomaly_id=ar.id,
        commodity_id=ar.commodity_id,
        commodity_name_kr=commodity_name,
        segment_id=ar.segment_id,
        segment_label_kr=segment_label,
        period=_period_str(ar.period),
        primary_pattern=ar.primary_pattern,
        pattern_types=ar.pattern_types or [ar.primary_pattern],
        confidence_grade=ar.confidence_grade,
        is_new=bool(ar.is_new),
        stat_metrics=stat_metrics,
        ml_summary=ml_summary,
        judgment_path=judgment_path,
    )


def _build_judgment_path(ar: AnomalyResult, sm: StatMetrics) -> list[JudgmentStep]:
    """판정 경로 5단계 — 통계 탐지·ML 합의·등급 결정 흐름."""
    steps: list[JudgmentStep] = [
        JudgmentStep(
            step=1, label="통계 탐지",
            value="탐지됨" if ar.stat_detected else "미탐지",
            passed=bool(ar.stat_detected),
        ),
        JudgmentStep(
            step=2, label="패턴 분류",
            value=ar.primary_pattern,
            passed=True,
        ),
        JudgmentStep(
            step=3, label="ML 합의 (3종)",
            value=f"{ar.ml_vote}/3",
            passed=bool(ar.ml_detected),
        ),
        JudgmentStep(
            step=4, label="통계·ML 일치",
            value="일치" if (ar.stat_detected and ar.ml_detected) else "불일치",
            passed=bool(ar.stat_detected and ar.ml_detected),
        ),
        JudgmentStep(
            step=5, label="신뢰도 등급",
            value=ar.confidence_grade,
            passed=ar.confidence_grade in ("high", "medium"),
        ),
    ]
    return steps


# ── /stat-series ─────────────────────────────────────────────────────────────

_METRIC_TO_COLS = {
    "transmission_rate": ["transmission_rate", "rolling_mean", "q1", "q3"],
    "zscore": ["zscore"],
    "ect": ["ect_or_spread", "ect_type"],
    "breakpoints": ["transmission_rate", "rolling_mean"],
}


async def get_stat_series(
    anomaly_id: int,
    metric: str,
    from_: str | None,
    to: str | None,
    granularity: str,
    db: AsyncSession,
) -> StatSeriesResponse:
    """지표별 인라인 시계열 — stat_timeseries 조회."""
    if metric in ("iqr", "asymmetry"):
        raise APIError(
            "API-MET-002",
            "metric=iqr/asymmetry 는 /stat-snapshot 엔드포인트를 사용하세요.",
            context={"metric": metric},
            http_status=400,
            public_code="SNAPSHOT_METRIC_ON_SERIES",
        )
    if metric not in _METRIC_TO_COLS:
        raise APIError(
            "API-MET-001",
            f"지원되지 않는 metric: {metric}",
            context={"metric": metric, "allowed": list(_METRIC_TO_COLS.keys())},
            http_status=400,
            public_code="INVALID_METRIC",
        )
    if granularity not in ("monthly", "quarterly", "yearly"):
        raise APIError(
            "API-MET-001",
            f"granularity 값이 올바르지 않습니다: {granularity}",
            context={"granularity": granularity},
            http_status=400,
            public_code="INVALID_GRANULARITY",
        )

    ar = await _get_anomaly_or_404(db, anomaly_id)

    # 기본 범위: anomaly period 기준 ±24개월
    if from_:
        period_from = _parse_yyyymm(from_, "from")
    else:
        # 24개월 전
        y, m = ar.period.year, ar.period.month - 24
        while m <= 0:
            m += 12
            y -= 1
        period_from = date(y, m, 1)
    if to:
        period_to = _parse_yyyymm(to, "to")
    else:
        y, m = ar.period.year, ar.period.month + 12
        while m > 12:
            m -= 12
            y += 1
        period_to = date(y, m, 1)

    if period_from > period_to:
        raise APIError(
            "API-MET-001", "from이 to보다 이후입니다.",
            context={"from": str(period_from), "to": str(period_to)},
            http_status=400, public_code="INVALID_DATE_RANGE",
        )

    rows = (await db.execute(
        select(StatTimeseries).where(and_(
            StatTimeseries.commodity_id == ar.commodity_id,
            StatTimeseries.segment_id == ar.segment_id,
            StatTimeseries.period >= period_from,
            StatTimeseries.period <= period_to,
        )).order_by(StatTimeseries.period)
    )).scalars().all()

    # bp_dates 조회 (metric=breakpoints 처리용)
    bp_set: set[date] = set()
    if metric == "breakpoints":
        bp = (await db.execute(
            select(Breakpoint).where(and_(
                Breakpoint.commodity_id == ar.commodity_id,
                Breakpoint.segment_id == ar.segment_id,
            ))
        )).scalar_one_or_none()
        if bp and bp.bp_dates:
            bp_set = set(bp.bp_dates)

    points = [
        StatSeriesPoint(
            period=_period_str(r.period),
            transmission_rate=_f(r.transmission_rate),
            rolling_mean=_f(r.rolling_mean),
            q1=_f(r.q1),
            q3=_f(r.q3),
            in_warmup_period=bool(r.in_warmup_period),
            is_breakpoint=(r.period in bp_set),
            zscore=_f(r.zscore),
            ect_or_spread=_f(r.ect_or_spread),
            ect_type=r.ect_type if r.ect_type in ("ECT", "log_spread") else None,
        )
        for r in rows
    ]

    actual_from = rows[0].period if rows else period_from
    actual_to = rows[-1].period if rows else period_to

    return StatSeriesResponse(
        anomaly_id=ar.id,
        commodity_id=ar.commodity_id,
        segment_id=ar.segment_id,
        metric=metric,
        highlight_period=_period_str(ar.period),
        requested_from=_period_str(period_from),
        requested_to=_period_str(period_to),
        actual_from=_period_str(actual_from),
        actual_to=_period_str(actual_to),
        granularity=granularity,
        total_points=len(points),
        data=points,
    )


# ── /stat-snapshot ───────────────────────────────────────────────────────────

async def get_stat_snapshot_iqr(
    anomaly_id: int, db: AsyncSession
) -> StatSnapshotIQRResponse:
    """metric=iqr — 해당 월 stat_timeseries의 IQR 박스플롯 데이터."""
    ar = await _get_anomaly_or_404(db, anomaly_id)
    stat = await _get_stat_at(db, ar.commodity_id, ar.segment_id, ar.period)
    if stat is None:
        raise APIError(
            "API-ANO-002",
            "해당 anomaly의 stat_timeseries 데이터가 없습니다.",
            context={"anomaly_id": anomaly_id, "period": _period_str(ar.period)},
            http_status=500, public_code="PIPELINE_DATA_MISSING",
        )
    # median 추정: rolling_mean 사용 (정밀 median은 별도 산출 필요)
    return StatSnapshotIQRResponse(
        anomaly_id=ar.id,
        metric="iqr",
        period=_period_str(ar.period),
        q1=_f(stat.q1),
        median=_f(stat.rolling_mean),
        q3=_f(stat.q3),
        iqr_lower=_f(stat.iqr_lower),
        iqr_upper=_f(stat.iqr_upper),
        current_value=_f(stat.transmission_rate),
        window_months=settings.rolling_window,
    )


async def get_stat_snapshot_asymmetry(
    anomaly_id: int, db: AsyncSession
) -> StatSnapshotAsymmetryResponse:
    """metric=asymmetry — 비대칭 검정 결과 + 상승/하락 표본."""
    ar = await _get_anomaly_or_404(db, anomaly_id)
    asym = (await db.execute(
        select(AsymmetryResult).where(and_(
            AsymmetryResult.commodity_id == ar.commodity_id,
            AsymmetryResult.segment_id == ar.segment_id,
        ))
    )).scalar_one_or_none()

    # 상승/하락 표본: stat_timeseries의 transmission_rate에서 upstream 방향별 분리
    ts_rows = (await db.execute(
        select(StatTimeseries).where(and_(
            StatTimeseries.commodity_id == ar.commodity_id,
            StatTimeseries.segment_id == ar.segment_id,
            StatTimeseries.in_warmup_period.is_(False),
        ))
    )).scalars().all()
    up_samples: list[float] = []
    down_samples: list[float] = []
    for r in ts_rows:
        tr = _f(r.transmission_rate)
        up = _f(r.upstream_pct)
        if tr is None or up is None:
            continue
        if up >= 0:
            up_samples.append(tr)
        else:
            down_samples.append(tr)

    return StatSnapshotAsymmetryResponse(
        anomaly_id=ar.id,
        metric="asymmetry",
        model_type=(asym.model_type if asym and asym.model_type in ("TECM", "asymmetric_VAR") else None),
        up_samples=up_samples,
        down_samples=down_samples,
        alpha_plus=_f(asym.alpha_plus) if asym else None,
        alpha_minus=_f(asym.alpha_minus) if asym else None,
        wald_pvalue=_f(asym.wald_pvalue) if asym else None,
        asymmetry_significant=(bool(asym.asymmetry_significant) if asym else None),
    )


# ── /irf ─────────────────────────────────────────────────────────────────────

async def get_irf(
    anomaly_id: int, include_subperiods: bool, db: AsyncSession
) -> IRFResponse:
    """IRF 곡선 — 전체 기간 + 옵션 시 하위 기간별."""
    ar = await _get_anomaly_or_404(db, anomaly_id)

    # 전체 기간 IRF (subperiod_id IS NULL)
    full_rows = (await db.execute(
        select(IRFData).where(and_(
            IRFData.commodity_id == ar.commodity_id,
            IRFData.segment_id == ar.segment_id,
            IRFData.subperiod_id.is_(None),
        )).order_by(IRFData.horizon)
    )).scalars().all()

    full_baseline = (await db.execute(
        select(Baseline).where(and_(
            Baseline.commodity_id == ar.commodity_id,
            Baseline.segment_id == ar.segment_id,
            Baseline.subperiod_id.is_(None),
        ))
    )).scalar_one_or_none()

    curves: list[IRFCurve] = []
    if full_rows:
        peak_h, peak_m = None, None
        for r in full_rows:
            if r.horizon == 0 and r.irf_peak_horizon is not None:
                peak_h = r.irf_peak_horizon
                peak_m = _f(r.irf_peak_magnitude)
                break
        curves.append(IRFCurve(
            scope="full",
            label="전체 기간",
            estimation_start=_period_str(full_baseline.estimation_start) if full_baseline else None,
            estimation_end=_period_str(full_baseline.estimation_end) if full_baseline else None,
            subperiod_index=None,
            peak_horizon=peak_h,
            peak_magnitude=peak_m,
            data=[
                IRFDataPoint(
                    horizon=int(r.horizon),
                    irf_downstream=_f(r.irf_downstream),
                    irf_lower_ci=_f(r.irf_lower_ci),
                    irf_upper_ci=_f(r.irf_upper_ci),
                )
                for r in full_rows
            ],
        ))

    if include_subperiods:
        # subperiods join irf_data
        subps = (await db.execute(
            select(Subperiod).where(and_(
                Subperiod.commodity_id == ar.commodity_id,
                Subperiod.segment_id == ar.segment_id,
            )).order_by(Subperiod.subperiod_index)
        )).scalars().all()
        for sp in subps:
            sp_rows = (await db.execute(
                select(IRFData).where(and_(
                    IRFData.subperiod_id == sp.id,
                )).order_by(IRFData.horizon)
            )).scalars().all()
            if not sp_rows:
                continue
            peak_h, peak_m = None, None
            for r in sp_rows:
                if r.horizon == 0 and r.irf_peak_horizon is not None:
                    peak_h = r.irf_peak_horizon
                    peak_m = _f(r.irf_peak_magnitude)
                    break
            curves.append(IRFCurve(
                scope="subperiod",
                label=f"하위 기간 {sp.subperiod_index}",
                estimation_start=_period_str(sp.period_start),
                estimation_end=_period_str(sp.period_end),
                subperiod_index=sp.subperiod_index,
                peak_horizon=peak_h,
                peak_magnitude=peak_m,
                data=[
                    IRFDataPoint(
                        horizon=int(r.horizon),
                        irf_downstream=_f(r.irf_downstream),
                        irf_lower_ci=_f(r.irf_lower_ci),
                        irf_upper_ci=_f(r.irf_upper_ci),
                    )
                    for r in sp_rows
                ],
            ))

    return IRFResponse(
        commodity_id=ar.commodity_id,
        segment_id=ar.segment_id,
        irfs=curves,
    )


# ── /ml-map ──────────────────────────────────────────────────────────────────

_MODEL_MAP = {
    "isolation_forest": "isolation_forest",
    "lof": "lof",
    "ocsvm": "ocsvm",
}


async def get_ml_map(
    anomaly_id: int,
    model: str,
    projection_method: str,
    db: AsyncSession,
) -> MLMapResponse:
    """ML 결과맵 2D 투영 — ml_projections 조회 (OI-15 보류 시 빈 응답)."""
    ar = await _get_anomaly_or_404(db, anomaly_id)
    model_name = _MODEL_MAP.get(model, model)

    rows = (await db.execute(
        select(MLProjection).where(and_(
            MLProjection.commodity_id == ar.commodity_id,
            MLProjection.segment_id == ar.segment_id,
            MLProjection.model_name == model_name,
            MLProjection.projection_method == projection_method,
        )).order_by(MLProjection.period)
    )).scalars().all()

    if not rows:
        # ML 결과 미산출 — OI-15 보류 상태, 빈 응답 반환 (404 대신 빈 points)
        return MLMapResponse(
            anomaly_id=ar.id,
            commodity_id=ar.commodity_id,
            segment_id=ar.segment_id,
            model=model,
            projection_method=projection_method,
            x_label="PC1",
            y_label="PC2",
            total_points=0,
            points=[],
        )

    from app.schemas.panel import MLMapPoint
    points = [
        MLMapPoint(
            period=_period_str(r.period),
            x_value=_f(r.x_value),
            y_value=_f(r.y_value),
            anomaly_score=_f(r.anomaly_score),
            is_anomaly=bool(r.is_anomaly),
            is_highlight=(r.period == ar.period),
        )
        for r in rows
    ]
    return MLMapResponse(
        anomaly_id=ar.id,
        commodity_id=ar.commodity_id,
        segment_id=ar.segment_id,
        model=model,
        projection_method=projection_method,
        x_label=rows[0].x_label or "PC1",
        y_label=rows[0].y_label or "PC2",
        total_points=len(points),
        points=points,
    )
