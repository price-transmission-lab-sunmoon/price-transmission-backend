"""서비스 레이어 — /anomalies/{id}/detail·stat-series·stat-snapshot·irf·ml-map
(feature_spec_API-PANEL §1.3 anomaly_panel.py 확정명).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import select
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
    MLMapPoint,
    MLMapResponse,
    StatSnapshotAsymmetryResponse,
    StatSnapshotIQRResponse,
)
from app.schemas.timeseries import StatSeriesPoint, StatSeriesResponse


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _to_yyyymm(d: date | None) -> str | None:
    return d.strftime("%Y-%m") if d else None


def _parse_yyyymm(s: str) -> date:
    """YYYY-MM → YYYY-MM-01 date 변환."""
    year, month = int(s[:4]), int(s[5:7])
    return date(year, month, 1)


async def _fetch_anomaly(anomaly_id: int, session: AsyncSession) -> AnomalyResult:
    """anomaly_results 조회. 미존재 시 API-ANO-001 (404)."""
    row = await session.get(AnomalyResult, anomaly_id)
    if row is None:
        raise APIError(
            "API-ANO-001",
            "요청한 이상 탐지 결과를 찾을 수 없습니다.",
            context={"anomaly_id": anomaly_id},
            http_status=404,
            public_code="ANOMALY_NOT_FOUND",
        )
    return row


async def _fetch_stat_ts(
    commodity_id: str,
    segment_id: str,
    period: date,
    session: AsyncSession,
) -> StatTimeseries:
    """해당 월 stat_timeseries 조회. 미존재 시 API-ANO-002 (500)."""
    result = await session.execute(
        select(StatTimeseries).where(
            StatTimeseries.commodity_id == commodity_id,
            StatTimeseries.segment_id == segment_id,
            StatTimeseries.period == period,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise APIError(
            "API-ANO-002",
            "파이프라인 통계 데이터가 누락되었습니다.",
            context={"commodity_id": commodity_id, "segment_id": segment_id, "period": str(period)},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )
    return row


# ── judgment_path 생성 (api_spec_vN §패널 엔드포인트 D-04 템플릿) ───────────

def _ml_step(anomaly: AnomalyResult) -> JudgmentStep:
    parts = []
    for label, flag in [("IF", anomaly.if_anomaly), ("LOF", anomaly.lof_anomaly), ("SVM", anomaly.svm_anomaly)]:
        parts.append(f"{label} {'✓' if flag else '✗'}")
    return JudgmentStep(
        step=5,
        label="ML 탐지",
        value=" / ".join(parts),
        passed=bool(anomaly.ml_detected),
    )


def _grade_step(grade: str) -> JudgmentStep:
    grade_text = {
        "high": "통계 O + ML 동시 확인 → 고신뢰",
        "medium": "통계 O + ML 미탐지 → 중신뢰",
        "reference": "ML O + 통계 미탐지 → 참고",
    }.get(grade, grade)
    return JudgmentStep(step=6, label="신뢰도 등급 확정", value=grade_text, passed=True)


def _build_judgment_path(
    anomaly: AnomalyResult,
    stat_ts: StatTimeseries,
) -> list[JudgmentStep]:
    patterns = list(anomaly.pattern_types or [])
    primary = anomaly.primary_pattern

    if len(patterns) == 1:
        if primary == "pattern1":
            steps = [
                JudgmentStep(step=1, label="전이율 산출",
                             value=f"해당 월 전이율 = {float(anomaly.transmission_rate or 0):.3f}", passed=True),
                JudgmentStep(step=2, label="방향 확인",
                             value="방향 역전" if anomaly.direction_reversal else "정방향", passed=True),
                JudgmentStep(step=3, label="시차 경과 확인",
                             value=f"기준 시차 {anomaly.normal_lag}개월, 실제 {anomaly.actual_lag}개월"
                             if anomaly.actual_lag is not None else f"기준 시차 {anomaly.normal_lag}개월",
                             passed=True),
                JudgmentStep(step=4, label="방향 역전/시차 이탈 판정",
                             value=str(anomaly.pattern1_flag_type or "탐지 확정"), passed=True),
            ]
        elif primary == "pattern2":
            zscore_val = float(stat_ts.zscore or 0)
            iqr_upper = float(stat_ts.iqr_upper or 0)
            steps = [
                JudgmentStep(step=1, label="전이율 산출",
                             value=f"해당 월 전이율 = {float(anomaly.transmission_rate or 0):.3f}", passed=True),
                JudgmentStep(step=2, label="롤링 Z-score",
                             value=f"{zscore_val:.2f} → {'경보' if anomaly.zscore_alert else '주의'} 기준({settings.zscore_alert if anomaly.zscore_alert else settings.zscore_warning}) 초과",
                             passed=anomaly.zscore_warning or anomaly.zscore_alert),
                JudgmentStep(step=3, label="IQR 판정",
                             value=f"Q3 + 1.5×IQR 상한({iqr_upper:.2f}) {'초과' if anomaly.iqr_outlier else '미달'}",
                             passed=anomaly.iqr_outlier),
                JudgmentStep(step=4, label="두 기준 동시 충족",
                             value="통계 경보 확정" if anomaly.stat_detected else "미충족",
                             passed=bool(anomaly.stat_detected)),
            ]
        else:  # pattern3
            steps = [
                JudgmentStep(step=1, label="국제가 안정 구간 진입",
                             value="월 변동 ±3% 이내 안정 구간", passed=True),
                JudgmentStep(step=2, label="스프레드 산출",
                             value=f"N={anomaly.pattern3_n} 누적 스프레드 = {float(anomaly.spread_n3_value or 0):.4f}",
                             passed=True),
                JudgmentStep(step=3, label="N개월 누적 확대 확인",
                             value="연속 확대 확인", passed=True),
                JudgmentStep(step=4, label="탐지 확정",
                             value="패턴 3 탐지", passed=True),
            ]
    else:
        # 복수 패턴: 각 패턴 판정을 순서대로
        steps = [
            JudgmentStep(step=i + 1, label=f"패턴 {p[-1]} 판정",
                         value=f"{p} 탐지", passed=True)
            for i, p in enumerate(patterns[:4])
        ]
        if len(steps) < 4:
            steps.append(JudgmentStep(step=4, label="복수 탐지 확정",
                                      value=f"{len(patterns)}개 패턴 동시 탐지", passed=True))

    steps.append(_ml_step(anomaly))
    steps.append(_grade_step(anomaly.confidence_grade))
    return steps


# ── 1. /detail ────────────────────────────────────────────────────────────────

async def get_detail(anomaly_id: int, session: AsyncSession) -> AnomalyDetailResponse:
    """패널 통합 데이터 조회 (feature_spec §3.1)."""
    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)
        stat_ts = await _fetch_stat_ts(anomaly.commodity_id, anomaly.segment_id, anomaly.period, session)

        # commodities JOIN → name_kr (commodity_id 는 String 필드, PK(id)가 아니므로 WHERE 사용)
        comm_result = await session.execute(
            select(Commodity).where(Commodity.commodity_id == anomaly.commodity_id)
        )
        commodity = comm_result.scalar_one_or_none()
        commodity_name_kr = commodity.name_kr if commodity else anomaly.commodity_id

        # segments JOIN → label_kr
        seg_result = await session.execute(
            select(Segment).where(Segment.segment_id == anomaly.segment_id)
        )
        seg = seg_result.scalar_one_or_none()
        segment_label_kr = seg.label_kr if seg else anomaly.segment_id

        # baselines — subperiod_id IS NULL (D-15: 전체 기간 기준선)
        bl_result = await session.execute(
            select(Baseline).where(
                Baseline.commodity_id == anomaly.commodity_id,
                Baseline.segment_id == anomaly.segment_id,
                Baseline.subperiod_id.is_(None),
            )
        )
        baseline = bl_result.scalar_one_or_none()

        # asymmetry_results
        asym_result = await session.execute(
            select(AsymmetryResult).where(
                AsymmetryResult.commodity_id == anomaly.commodity_id,
                AsymmetryResult.segment_id == anomaly.segment_id,
            )
        )
        asym = asym_result.scalar_one_or_none()

        # cointegration_results — UNIQUE (commodity_id, segment_id), 행 1개
        coint_result = await session.execute(
            select(CointegrationResult).where(
                CointegrationResult.commodity_id == anomaly.commodity_id,
                CointegrationResult.segment_id == anomaly.segment_id,
            )
        )
        coint = coint_result.scalar_one_or_none()

        # ml_scores — 조인 키: (commodity_id, segment_id, period)
        ml_result = await session.execute(
            select(MLScore).where(
                MLScore.commodity_id == anomaly.commodity_id,
                MLScore.segment_id == anomaly.segment_id,
                MLScore.period == anomaly.period,
            )
        )
        ml = ml_result.scalar_one_or_none()

        # subperiod_index (anomaly.subperiod_id → subperiods)
        subperiod_index: int | None = None
        if anomaly.subperiod_id is not None:
            sp = await session.get(Subperiod, anomaly.subperiod_id)
            subperiod_index = sp.subperiod_index if sp else None

        # breakpoints.bp_dates (D-16)
        bp_result = await session.execute(
            select(Breakpoint).where(
                Breakpoint.commodity_id == anomaly.commodity_id,
                Breakpoint.segment_id == anomaly.segment_id,
            )
        )
        bp = bp_result.scalar_one_or_none()
        bp_dates = [_to_yyyymm(d) for d in (bp.bp_dates or [])] if bp else []

        stat_metrics = StatMetrics(
            transmission_rate=float(anomaly.transmission_rate) if anomaly.transmission_rate is not None else None,
            rolling_mean=float(stat_ts.rolling_mean) if stat_ts.rolling_mean is not None else None,
            zscore=float(stat_ts.zscore) if stat_ts.zscore is not None else None,
            zscore_warning=bool(anomaly.zscore_warning),
            zscore_alert=bool(anomaly.zscore_alert),
            zscore_threshold_warning=settings.zscore_warning,
            zscore_threshold_alert=settings.zscore_alert,
            q1=float(stat_ts.q1) if stat_ts.q1 is not None else None,
            q3=float(stat_ts.q3) if stat_ts.q3 is not None else None,
            iqr_lower=float(stat_ts.iqr_lower) if stat_ts.iqr_lower is not None else None,
            iqr_upper=float(stat_ts.iqr_upper) if stat_ts.iqr_upper is not None else None,
            iqr_outlier=bool(anomaly.iqr_outlier),
            over_transmission=bool(anomaly.over_transmission),
            under_transmission=bool(anomaly.under_transmission),
            normal_lag=int(baseline.normal_transmission_lag) if baseline else None,
            actual_lag=int(anomaly.actual_lag) if anomaly.actual_lag is not None else None,
            direction_reversal=bool(anomaly.direction_reversal),
            lag_deviation=bool(anomaly.lag_deviation),
            pattern1_flag_type=anomaly.pattern1_flag_type,
            ect_or_spread=float(stat_ts.ect_or_spread) if stat_ts.ect_or_spread is not None else None,
            ect_type=stat_ts.ect_type,
            spread_n3=float(stat_ts.spread_n3) if stat_ts.spread_n3 is not None else None,
            alpha_plus=float(asym.alpha_plus) if asym and asym.alpha_plus is not None else None,
            alpha_minus=float(asym.alpha_minus) if asym and asym.alpha_minus is not None else None,
            wald_pvalue=float(asym.wald_pvalue) if asym and asym.wald_pvalue is not None else None,
            asymmetry_significant=bool(asym.asymmetry_significant) if asym else None,
            rocket_feather_direction=asym.rocket_feather_direction if asym else None,
            model_type=coint.model_type if coint else (baseline.model_type if baseline else None),
            cointegrated=bool(coint.cointegrated) if coint else None,
            subperiod_index=subperiod_index,
            bp_dates=[d for d in bp_dates if d is not None],
        )

        ml_summary = MLSummary(
            ml_vote=int(anomaly.ml_vote),
            ml_detected=bool(anomaly.ml_detected),
            if_anomaly=bool(anomaly.if_anomaly) if anomaly.if_anomaly is not None else None,
            if_score=float(ml.if_score) if ml and ml.if_score is not None else None,
            if_percentile=float(ml.if_percentile) if ml and ml.if_percentile is not None else None,
            lof_anomaly=bool(anomaly.lof_anomaly) if anomaly.lof_anomaly is not None else None,
            lof_score=float(ml.lof_score) if ml and ml.lof_score is not None else None,
            lof_percentile=float(ml.lof_percentile) if ml and ml.lof_percentile is not None else None,
            svm_anomaly=bool(anomaly.svm_anomaly) if anomaly.svm_anomaly is not None else None,
            svm_score=float(ml.svm_score) if ml and ml.svm_score is not None else None,
            svm_percentile=float(ml.svm_percentile) if ml and ml.svm_percentile is not None else None,
        )

        judgment_path = _build_judgment_path(anomaly, stat_ts)

        return AnomalyDetailResponse(
            anomaly_id=anomaly.id,
            commodity_id=anomaly.commodity_id,
            commodity_name_kr=commodity_name_kr,
            segment_id=anomaly.segment_id,
            segment_label_kr=segment_label_kr,
            period=_to_yyyymm(anomaly.period),
            primary_pattern=anomaly.primary_pattern,
            pattern_types=list(anomaly.pattern_types),
            confidence_grade=anomaly.confidence_grade,
            is_new=bool(anomaly.is_new),
            stat_metrics=stat_metrics,
            ml_summary=ml_summary,
            judgment_path=judgment_path,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001",
            "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from exc


# ── 2. /stat-series ───────────────────────────────────────────────────────────

_SNAPSHOT_METRICS = {"iqr", "asymmetry"}


async def get_stat_series(
    anomaly_id: int,
    metric: str,
    from_str: str | None,
    to_str: str | None,
    granularity: Literal["monthly", "quarterly", "yearly"],
    session: AsyncSession,
) -> StatSeriesResponse:
    """지표별 인라인 시계열 (api_spec_vN §stat-series)."""
    if metric in _SNAPSHOT_METRICS:
        raise APIError(
            "API-MET-002",
            f"'{metric}'은 스냅샷 전용 지표입니다. /stat-snapshot 엔드포인트를 사용하세요.",
            context={"metric": metric},
            http_status=400,
            public_code="SNAPSHOT_METRIC_ON_SERIES",
        )

    allowed = {"transmission_rate", "zscore", "ect", "breakpoints"}
    if metric not in allowed:
        raise APIError(
            "API-MET-001",
            f"허용되지 않는 metric 값입니다: {metric!r}",
            context={"metric": metric, "allowed": sorted(allowed)},
            http_status=400,
            public_code="INVALID_METRIC",
        )

    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)

        # 날짜 범위 파싱
        from_date = _parse_yyyymm(from_str) if from_str else None
        to_date = _parse_yyyymm(to_str) if to_str else None
        if from_date and to_date and from_date > to_date:
            raise APIError(
                "API-STR-002",
                "from이 to보다 클 수 없습니다.",
                context={"from": from_str, "to": to_str},
                http_status=400,
                public_code="INVALID_DATE_RANGE",
            )

        # stat_timeseries 조회
        stmt = select(StatTimeseries).where(
            StatTimeseries.commodity_id == anomaly.commodity_id,
            StatTimeseries.segment_id == anomaly.segment_id,
        )
        if from_date:
            stmt = stmt.where(StatTimeseries.period >= from_date)
        if to_date:
            stmt = stmt.where(StatTimeseries.period <= to_date)
        stmt = stmt.order_by(StatTimeseries.period)

        result = await session.execute(stmt)
        rows = result.scalars().all()

        # breakpoints.bp_dates (metric=breakpoints 또는 transmission_rate 시 is_breakpoint 표시)
        bp_dates_set: set[date] = set()
        if metric == "breakpoints":
            bp_res = await session.execute(
                select(Breakpoint).where(
                    Breakpoint.commodity_id == anomaly.commodity_id,
                    Breakpoint.segment_id == anomaly.segment_id,
                )
            )
            bp = bp_res.scalar_one_or_none()
            if bp and bp.bp_dates:
                bp_dates_set = set(bp.bp_dates)

        data: list[StatSeriesPoint] = []
        for row in rows:
            point = StatSeriesPoint(
                period=_to_yyyymm(row.period),
                in_warmup_period=bool(row.in_warmup_period),
                is_breakpoint=row.period in bp_dates_set,
            )
            if metric in ("transmission_rate", "breakpoints"):
                point.transmission_rate = float(row.transmission_rate) if row.transmission_rate is not None else None
                point.rolling_mean = float(row.rolling_mean) if row.rolling_mean is not None else None
                point.q1 = float(row.q1) if row.q1 is not None else None
                point.q3 = float(row.q3) if row.q3 is not None else None
            elif metric == "zscore":
                point.zscore = float(row.zscore) if row.zscore is not None else None
            elif metric == "ect":
                point.ect_or_spread = float(row.ect_or_spread) if row.ect_or_spread is not None else None
                point.ect_type = row.ect_type
            data.append(point)

        # granularity 집계 (monthly가 아닌 경우)
        if granularity != "monthly":
            data = _aggregate_stat_series(data, granularity)

        actual_from = data[0].period if data else (from_str or "")
        actual_to = data[-1].period if data else (to_str or "")

        return StatSeriesResponse(
            anomaly_id=anomaly_id,
            commodity_id=anomaly.commodity_id,
            segment_id=anomaly.segment_id,
            metric=metric,
            highlight_period=_to_yyyymm(anomaly.period),
            requested_from=from_str or actual_from,
            requested_to=to_str or actual_to,
            actual_from=actual_from,
            actual_to=actual_to,
            granularity=granularity,
            total_points=len(data),
            data=data,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001",
            "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from exc


def _aggregate_stat_series(
    data: list[StatSeriesPoint],
    granularity: Literal["quarterly", "yearly"],
) -> list[StatSeriesPoint]:
    """monthly 데이터를 quarterly/yearly로 단순 평균 집계."""
    from collections import defaultdict

    def _bucket(period: str) -> str:
        year, month = period[:4], int(period[5:7])
        if granularity == "yearly":
            return f"{year}-01"
        q = (month - 1) // 3 + 1
        return f"{year}-{q * 3 - 2:02d}"

    buckets: dict[str, list[StatSeriesPoint]] = defaultdict(list)
    for p in data:
        buckets[_bucket(p.period)].append(p)

    def _avg(vals: list) -> float | None:
        clean = [v for v in vals if v is not None]
        return sum(clean) / len(clean) if clean else None

    result = []
    for key in sorted(buckets):
        group = buckets[key]
        merged = StatSeriesPoint(
            period=key,
            in_warmup_period=any(p.in_warmup_period for p in group),
            is_breakpoint=any(p.is_breakpoint for p in group),
            transmission_rate=_avg([p.transmission_rate for p in group]),
            rolling_mean=_avg([p.rolling_mean for p in group]),
            q1=_avg([p.q1 for p in group]),
            q3=_avg([p.q3 for p in group]),
            zscore=_avg([p.zscore for p in group]),
            ect_or_spread=_avg([p.ect_or_spread for p in group]),
            ect_type=group[0].ect_type if group else None,
        )
        result.append(merged)
    return result


# ── 3. /stat-snapshot ────────────────────────────────────────────────────────

async def get_stat_snapshot_iqr(
    anomaly_id: int,
    session: AsyncSession,
) -> StatSnapshotIQRResponse:
    """IQR 박스플롯 스냅샷 (metric=iqr)."""
    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)
        stat_ts = await _fetch_stat_ts(anomaly.commodity_id, anomaly.segment_id, anomaly.period, session)

        return StatSnapshotIQRResponse(
            anomaly_id=anomaly_id,
            metric="iqr",
            period=_to_yyyymm(anomaly.period),
            q1=float(stat_ts.q1) if stat_ts.q1 is not None else None,
            median=float(stat_ts.rolling_mean) if stat_ts.rolling_mean is not None else None,
            q3=float(stat_ts.q3) if stat_ts.q3 is not None else None,
            iqr_lower=float(stat_ts.iqr_lower) if stat_ts.iqr_lower is not None else None,
            iqr_upper=float(stat_ts.iqr_upper) if stat_ts.iqr_upper is not None else None,
            current_value=float(stat_ts.transmission_rate) if stat_ts.transmission_rate is not None else None,
            window_months=settings.rolling_window,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001", "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id}, http_status=500, public_code="INTERNAL_ERROR",
        ) from exc


async def get_stat_snapshot_asymmetry(
    anomaly_id: int,
    session: AsyncSession,
) -> StatSnapshotAsymmetryResponse:
    """비대칭 히스토그램 스냅샷 (metric=asymmetry).

    up_samples/down_samples: stat_timeseries.upstream_pct 양/음수 구간의 transmission_rate 목록.
    """
    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)

        asym_result = await session.execute(
            select(AsymmetryResult).where(
                AsymmetryResult.commodity_id == anomaly.commodity_id,
                AsymmetryResult.segment_id == anomaly.segment_id,
            )
        )
        asym = asym_result.scalar_one_or_none()

        # stat_timeseries 전체 기간 조회 → upstream_pct 기준 상승/하락 구간 분류
        ts_result = await session.execute(
            select(StatTimeseries).where(
                StatTimeseries.commodity_id == anomaly.commodity_id,
                StatTimeseries.segment_id == anomaly.segment_id,
                StatTimeseries.in_warmup_period.is_(False),
            ).order_by(StatTimeseries.period)
        )
        ts_rows = ts_result.scalars().all()

        up_samples = [
            float(r.transmission_rate)
            for r in ts_rows
            if r.upstream_pct is not None and r.upstream_pct > 0
            and r.transmission_rate is not None
        ]
        down_samples = [
            float(r.transmission_rate)
            for r in ts_rows
            if r.upstream_pct is not None and r.upstream_pct <= 0
            and r.transmission_rate is not None
        ]

        return StatSnapshotAsymmetryResponse(
            anomaly_id=anomaly_id,
            metric="asymmetry",
            model_type=asym.model_type if asym else None,
            up_samples=up_samples,
            down_samples=down_samples,
            alpha_plus=float(asym.alpha_plus) if asym and asym.alpha_plus is not None else None,
            alpha_minus=float(asym.alpha_minus) if asym and asym.alpha_minus is not None else None,
            wald_pvalue=float(asym.wald_pvalue) if asym and asym.wald_pvalue is not None else None,
            asymmetry_significant=bool(asym.asymmetry_significant) if asym else None,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001", "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id}, http_status=500, public_code="INTERNAL_ERROR",
        ) from exc


# ── 4. /irf ──────────────────────────────────────────────────────────────────

async def get_irf(
    anomaly_id: int,
    include_subperiods: bool,
    session: AsyncSession,
) -> IRFResponse:
    """IRF 차트 데이터 (전체 기간 + 하위 기간별)."""
    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)

        # irf_data 전체 조회 (subperiod_id IS NULL = 전체 기간, NOT NULL = 하위 기간)
        stmt = select(IRFData).where(
            IRFData.commodity_id == anomaly.commodity_id,
            IRFData.segment_id == anomaly.segment_id,
        ).order_by(IRFData.subperiod_id.nullsfirst(), IRFData.horizon)

        if not include_subperiods:
            stmt = stmt.where(IRFData.subperiod_id.is_(None))

        irf_result = await session.execute(stmt)
        irf_rows = irf_result.scalars().all()

        # subperiod_id → Subperiod 매핑 (label·기간 생성용)
        subperiod_map: dict[int, Subperiod] = {}
        if include_subperiods:
            sp_ids = {r.subperiod_id for r in irf_rows if r.subperiod_id is not None}
            for sp_id in sp_ids:
                sp = await session.get(Subperiod, sp_id)
                if sp:
                    subperiod_map[sp_id] = sp

        # subperiod_id 별로 그룹핑
        from collections import defaultdict
        groups: dict[int | None, list[IRFData]] = defaultdict(list)
        for row in irf_rows:
            groups[row.subperiod_id].append(row)

        curves: list[IRFCurve] = []

        # 전체 기간 (subperiod_id IS NULL)
        full_rows = groups.get(None, [])
        if full_rows:
            peak_row = next((r for r in full_rows if r.horizon == 0), full_rows[0])
            curves.append(IRFCurve(
                scope="full",
                label="전체 기간",
                estimation_start=None,
                estimation_end=None,
                peak_horizon=int(peak_row.irf_peak_horizon) if peak_row.irf_peak_horizon is not None else None,
                peak_magnitude=float(peak_row.irf_peak_magnitude) if peak_row.irf_peak_magnitude is not None else None,
                data=[
                    IRFDataPoint(
                        horizon=r.horizon,
                        irf_downstream=float(r.irf_downstream),
                        irf_lower_ci=float(r.irf_lower_ci) if r.irf_lower_ci is not None else None,
                        irf_upper_ci=float(r.irf_upper_ci) if r.irf_upper_ci is not None else None,
                    )
                    for r in sorted(full_rows, key=lambda x: x.horizon)
                ],
            ))

        # 하위 기간별
        for sp_id, sp_rows in sorted(groups.items(), key=lambda x: (x[0] is None, x[0])):
            if sp_id is None:
                continue
            sp = subperiod_map.get(sp_id)
            peak_row = next((r for r in sp_rows if r.horizon == 0), sp_rows[0])
            label = (
                f"{_to_yyyymm(sp.period_start)} ~ {_to_yyyymm(sp.period_end)}"
                if sp else f"하위 기간 {sp_id}"
            )
            curves.append(IRFCurve(
                scope="subperiod",
                label=label,
                estimation_start=_to_yyyymm(sp.period_start) if sp else None,
                estimation_end=_to_yyyymm(sp.period_end) if sp else None,
                subperiod_index=int(sp.subperiod_index) if sp else None,
                peak_horizon=int(peak_row.irf_peak_horizon) if peak_row.irf_peak_horizon is not None else None,
                peak_magnitude=float(peak_row.irf_peak_magnitude) if peak_row.irf_peak_magnitude is not None else None,
                data=[
                    IRFDataPoint(
                        horizon=r.horizon,
                        irf_downstream=float(r.irf_downstream),
                        irf_lower_ci=float(r.irf_lower_ci) if r.irf_lower_ci is not None else None,
                        irf_upper_ci=float(r.irf_upper_ci) if r.irf_upper_ci is not None else None,
                    )
                    for r in sorted(sp_rows, key=lambda x: x.horizon)
                ],
            ))

        return IRFResponse(
            commodity_id=anomaly.commodity_id,
            segment_id=anomaly.segment_id,
            irfs=curves,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001", "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id}, http_status=500, public_code="INTERNAL_ERROR",
        ) from exc


# ── 5. /ml-map ───────────────────────────────────────────────────────────────

async def get_ml_map(
    anomaly_id: int,
    model: Literal["isolation_forest", "lof", "ocsvm"],
    projection_method: Literal["pca", "feature_direct"],
    session: AsyncSession,
) -> MLMapResponse:
    """ML 결과맵 2D 투영 데이터 (api_spec_vN §ml-map)."""
    try:
        anomaly = await _fetch_anomaly(anomaly_id, session)

        result = await session.execute(
            select(MLProjection).where(
                MLProjection.commodity_id == anomaly.commodity_id,
                MLProjection.segment_id == anomaly.segment_id,
                MLProjection.model_name == model,
                MLProjection.projection_method == projection_method,
            ).order_by(MLProjection.period)
        )
        proj_rows = result.scalars().all()

        if not proj_rows:
            raise APIError(
                "API-ANO-003",
                "ML 투영 데이터가 아직 산출되지 않았습니다.",
                context={"anomaly_id": anomaly_id, "model": model},
                http_status=404,
                public_code="ML_MAP_NOT_READY",
            )

        x_label = proj_rows[0].x_label or "PC1"
        y_label = proj_rows[0].y_label or "PC2"

        points = [
            MLMapPoint(
                period=_to_yyyymm(r.period),
                x_value=float(r.x_value),
                y_value=float(r.y_value),
                anomaly_score=float(r.anomaly_score) if r.anomaly_score is not None else None,
                is_anomaly=bool(r.is_anomaly) if r.is_anomaly is not None else False,
                is_highlight=(r.period == anomaly.period),  # 해당 이상 탐지 월 강조
            )
            for r in proj_rows
        ]

        return MLMapResponse(
            anomaly_id=anomaly_id,
            commodity_id=anomaly.commodity_id,
            segment_id=anomaly.segment_id,
            model=model,
            projection_method=projection_method,
            x_label=x_label,
            y_label=y_label,
            total_points=len(points),
            points=points,
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(
            "API-INT-001", "내부 예외 처리 실패",
            context={"anomaly_id": anomaly_id}, http_status=500, public_code="INTERNAL_ERROR",
        ) from exc
