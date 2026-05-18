"""비즈니스 로직 — 분석 수치 패널 5개 엔드포인트 (feature_spec_API-PANEL_vN §1.3).

GET /anomalies/{id}/detail        — 다중 테이블 조인·judgment_path 생성
GET /anomalies/{id}/stat-series   — metric 4종 시계열
GET /anomalies/{id}/stat-snapshot — iqr·asymmetry 스냅샷
GET /anomalies/{id}/irf           — 전체+하위기간 IRF 곡선
GET /anomalies/{id}/ml-map        — model 파라미터 분기 투영 데이터
"""
from __future__ import annotations

import logging
from datetime import date
from itertools import groupby

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
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

logger = logging.getLogger("app")

# ── metric 허용값 ─────────────────────────────────────────────────────────────
_SERIES_METRICS = {"transmission_rate", "zscore", "ect", "breakpoints"}
_SNAPSHOT_METRICS = {"iqr", "asymmetry"}
_SNAPSHOT_ONLY = {"iqr", "asymmetry"}  # stat-series에 요청 시 SNAPSHOT_METRIC_ON_SERIES


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _parse_yyyymm(s: str) -> date:
    """'YYYY-MM' → date(year, month, 1)."""
    try:
        year, month = s.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, TypeError) as e:
        raise APIError(
            "API-VAL-001",
            f"날짜 형식이 올바르지 않습니다 (YYYY-MM 필요): {s!r}",
            context={"value": s},
            http_status=400,
            public_code="API-VAL-001",
        ) from e


def _to_float(v: object) -> float | None:
    return float(v) if v is not None else None


def _to_yyyymm(d: date | None) -> str | None:
    return d.strftime("%Y-%m") if d else None


# ── 공통 조회 헬퍼 ─────────────────────────────────────────────────────────────

async def _get_anomaly_and_segment(
    db: AsyncSession,
    anomaly_id: int,
) -> tuple[AnomalyResult, Segment]:
    """anomaly 조회 + segment 검증. API-ANO-001 / API-SEG-001 발생."""
    anomaly = await db.get(AnomalyResult, anomaly_id)
    if not anomaly:
        raise APIError(
            "API-ANO-001",
            "요청한 이상 탐지 결과를 찾을 수 없습니다.",
            context={"anomaly_id": anomaly_id},
            http_status=404,
            public_code="ANOMALY_NOT_FOUND",
        )

    segment = (
        await db.execute(
            select(Segment).where(Segment.segment_id == anomaly.segment_id)
        )
    ).scalar_one_or_none()

    if not segment:
        raise APIError(
            "API-SEG-001",
            "이상 탐지 결과가 참조하는 구간이 유효하지 않습니다.",
            context={"anomaly_id": anomaly_id, "segment_id": anomaly.segment_id},
            http_status=400,
            public_code="INVALID_SEGMENT",
        )

    return anomaly, segment


# ── judgment_path 생성 (D-04) ─────────────────────────────────────────────────

def _build_judgment_path(
    anomaly: AnomalyResult,
    stat_ts: StatTimeseries,
    ml_summary: MLSummary,
    settings: Settings,
) -> list[JudgmentStep]:
    """패턴 유형별 템플릿에 따라 판정 경로 6단계를 동적으로 생성 (api_spec_vN D-04)."""
    patterns: list[str] = list(anomaly.pattern_types or [anomaly.primary_pattern])
    is_multi = len(patterns) > 1
    steps: list[JudgmentStep] = []

    # ── Steps 1~4: 패턴별 ──────────────────────────────────────────────────
    tr = _to_float(anomaly.transmission_rate)
    tr_str = f"{tr:.2f}" if tr is not None else "산출값 없음"

    if is_multi:
        steps.append(JudgmentStep(
            step=1, label="전이율 산출",
            value=f"해당 월 전이율 = {tr_str}", passed=True,
        ))
        pattern_descs: list[str] = []
        for p in patterns:
            if p == "pattern1":
                flag = anomaly.pattern1_flag_type or ""
                flag_label = {"direction_reversal": "방향 역전", "lag_deviation": "시차 이탈",
                              "both": "방향 역전 + 시차 이탈"}.get(flag, "이상 탐지")
                pattern_descs.append(f"패턴1({flag_label})")
            elif p == "pattern2":
                z = _to_float(stat_ts.zscore) if stat_ts else None
                pattern_descs.append(f"패턴2(Z={z:.2f})" if z is not None else "패턴2")
            elif p == "pattern3":
                n = anomaly.pattern3_n or 3
                pattern_descs.append(f"패턴3(N={n}개월)")
        steps.append(JudgmentStep(
            step=2, label="패턴별 판정",
            value=" / ".join(pattern_descs), passed=True,
        ))
        steps.append(JudgmentStep(
            step=3, label="복합 검증",
            value=f"{len(patterns)}개 패턴 신호 동시 확인", passed=True,
        ))
        steps.append(JudgmentStep(
            step=4, label="복수 탐지 확정",
            value=f"{len(patterns)}개 패턴 복합 이상 탐지 확정", passed=True,
        ))

    elif "pattern1" in patterns:
        steps.append(JudgmentStep(
            step=1, label="전이율 산출",
            value=f"해당 월 전이율 = {tr_str}", passed=True,
        ))
        dir_rev = anomaly.direction_reversal
        steps.append(JudgmentStep(
            step=2, label="방향 확인",
            value=f"방향 역전 {'확인됨' if dir_rev else '없음'}",
            passed=bool(dir_rev),
        ))
        actual = anomaly.actual_lag
        normal = anomaly.normal_lag
        lag_dev = anomaly.lag_deviation
        lag_desc = (
            f"정상 시차 {normal}개월 / 실제 {actual}개월 → 이탈 확인"
            if actual is not None and normal is not None and lag_dev
            else ("시차 이탈 없음" if not lag_dev else "시차 이탈 확인")
        )
        steps.append(JudgmentStep(
            step=3, label="시차 경과 확인",
            value=lag_desc, passed=bool(lag_dev),
        ))
        flag = anomaly.pattern1_flag_type or ""
        flag_label = {"direction_reversal": "방향 역전", "lag_deviation": "시차 이탈",
                      "both": "방향 역전 + 시차 이탈"}.get(flag, "이상 탐지")
        steps.append(JudgmentStep(
            step=4, label="방향 역전/시차 이탈 판정",
            value=f"패턴 1 확정 — {flag_label}", passed=True,
        ))

    elif "pattern2" in patterns:
        steps.append(JudgmentStep(
            step=1, label="전이율 산출",
            value=f"해당 월 전이율 = {tr_str}", passed=True,
        ))
        z = _to_float(stat_ts.zscore) if stat_ts else None
        z_str = f"{z:.2f}" if z is not None else "—"
        threshold = settings.zscore_alert if anomaly.zscore_alert else settings.zscore_warning
        steps.append(JudgmentStep(
            step=2, label="롤링 Z-score",
            value=f"{z_str} → {'경보' if anomaly.zscore_alert else '주의'} 기준({threshold}) 초과",
            passed=bool(anomaly.zscore_warning or anomaly.zscore_alert),
        ))
        iqr_upper = _to_float(stat_ts.iqr_upper) if stat_ts else None
        iqr_desc = (
            f"Q3 + 1.5×IQR 상한({iqr_upper:.2f}) {'초과' if anomaly.iqr_outlier else '미초과'}"
            if iqr_upper is not None
            else "IQR 이상치 판정"
        )
        steps.append(JudgmentStep(
            step=3, label="IQR 판정",
            value=iqr_desc, passed=bool(anomaly.iqr_outlier),
        ))
        both = (anomaly.zscore_warning or anomaly.zscore_alert) and anomaly.iqr_outlier
        steps.append(JudgmentStep(
            step=4, label="두 기준 동시 충족",
            value="Z-score·IQR 두 기준 동시 충족 — 통계 경보 확정" if both else "부분 기준만 충족",
            passed=bool(both),
        ))

    elif "pattern3" in patterns:
        steps.append(JudgmentStep(
            step=1, label="국제가 안정 구간 진입",
            value="국제가 월 변동 ±3% 이내", passed=True,
        ))
        n3 = _to_float(anomaly.spread_n3_value)
        steps.append(JudgmentStep(
            step=2, label="스프레드 산출",
            value=f"N=3 기준 누적 스프레드 = {n3:.4f}" if n3 is not None else "스프레드 산출",
            passed=True,
        ))
        n = anomaly.pattern3_n or 3
        steps.append(JudgmentStep(
            step=3, label="N개월 누적 확대 확인",
            value=f"{n}개월 연속 같은 방향 확대 확인", passed=True,
        ))
        steps.append(JudgmentStep(
            step=4, label="탐지 확정",
            value="패턴 3 이상 탐지 확정", passed=True,
        ))

    else:
        # fallback
        steps.extend([
            JudgmentStep(step=1, label="이상 신호 확인", value="통계 기반 이상 탐지", passed=True),
            JudgmentStep(step=2, label="검증", value="추가 검증 수행", passed=True),
            JudgmentStep(step=3, label="확인", value="이상 확인", passed=True),
            JudgmentStep(step=4, label="탐지 확정", value="이상 탐지 확정", passed=True),
        ])

    # ── Step 5: ML 탐지 ────────────────────────────────────────────────────
    votes = []
    if_a = ml_summary.if_anomaly
    lof_a = ml_summary.lof_anomaly
    svm_a = ml_summary.svm_anomaly
    if if_a is not None:
        votes.append(f"IF {'✓' if if_a else '✗'}")
    if lof_a is not None:
        votes.append(f"LOF {'✓' if lof_a else '✗'}")
    if svm_a is not None:
        votes.append(f"SVM {'✓' if svm_a else '✗'}")
    vote_str = " / ".join(votes) if votes else "ML 판정 없음"
    steps.append(JudgmentStep(
        step=5, label="ML 탐지",
        value=vote_str, passed=ml_summary.ml_detected,
    ))

    # ── Step 6: 신뢰도 등급 확정 ───────────────────────────────────────────
    grade_desc = {
        "high": "통계 O + ML 동시 확인 → 고신뢰",
        "medium": "통계 O + ML 미탐지 → 중신뢰",
        "reference": "ML O + 통계 미탐지 → 참고",
    }.get(anomaly.confidence_grade, anomaly.confidence_grade)
    steps.append(JudgmentStep(
        step=6, label="신뢰도 등급 확정",
        value=grade_desc, passed=True,
    ))

    return steps


# ── 집계 헬퍼 (stat-series granularity) ─────────────────────────────────────

def _group_key(row: StatTimeseries, granularity: str) -> tuple:
    p: date = row.period
    if granularity == "quarterly":
        return (p.year, (p.month - 1) // 3 + 1)
    return (p.year,)  # yearly


def _group_period_label(key: tuple, granularity: str) -> str:
    if granularity == "quarterly":
        year, q = key
        return f"{year}-{q * 3:02d}"
    return f"{key[0]}-12"


def _avg(vals: list[float | None]) -> float | None:
    filtered = [v for v in vals if v is not None]
    return sum(filtered) / len(filtered) if filtered else None


def _rows_to_series_points(
    rows: list[StatTimeseries],
    metric: str,
    granularity: str,
    bp_dates_set: set[date],
) -> list[StatSeriesPoint]:
    """stat_timeseries 행 목록 → StatSeriesPoint 목록 (granularity 집계 포함)."""
    if granularity == "monthly":
        points: list[StatSeriesPoint] = []
        for row in rows:
            p_label = _to_yyyymm(row.period)
            is_bp = row.period in bp_dates_set
            points.append(StatSeriesPoint(
                period=p_label,
                transmission_rate=_to_float(row.transmission_rate),
                rolling_mean=_to_float(row.rolling_mean),
                q1=_to_float(row.q1),
                q3=_to_float(row.q3),
                in_warmup_period=row.in_warmup_period,
                is_breakpoint=is_bp,
                zscore=_to_float(row.zscore),
                ect_or_spread=_to_float(row.ect_or_spread),
                ect_type=row.ect_type,
            ))
        return points

    # quarterly / yearly: 집계
    def sort_key(r: StatTimeseries) -> tuple:
        return _group_key(r, granularity)

    sorted_rows = sorted(rows, key=sort_key)
    result: list[StatSeriesPoint] = []

    for key, group_iter in groupby(sorted_rows, key=sort_key):
        group = list(group_iter)
        p_label = _group_period_label(key, granularity)
        is_bp = any(r.period in bp_dates_set for r in group)
        result.append(StatSeriesPoint(
            period=p_label,
            transmission_rate=_avg([_to_float(r.transmission_rate) for r in group]),
            rolling_mean=_avg([_to_float(r.rolling_mean) for r in group]),
            q1=_avg([_to_float(r.q1) for r in group]),
            q3=_avg([_to_float(r.q3) for r in group]),
            in_warmup_period=any(r.in_warmup_period for r in group),
            is_breakpoint=is_bp,
            zscore=_avg([_to_float(r.zscore) for r in group]),
            ect_or_spread=_avg([_to_float(r.ect_or_spread) for r in group]),
            ect_type=group[0].ect_type if group else None,
        ))
    return result


# ── 서비스 함수 ───────────────────────────────────────────────────────────────

async def get_panel_detail(
    db: AsyncSession,
    anomaly_id: int,
    settings: Settings,
) -> AnomalyDetailResponse:
    """GET /anomalies/{id}/detail — 다중 테이블 조인 + judgment_path 생성."""
    anomaly, segment = await _get_anomaly_and_segment(db, anomaly_id)

    # stat_timeseries (해당 월)
    stat_ts = (
        await db.execute(
            select(StatTimeseries).where(
                StatTimeseries.commodity_id == anomaly.commodity_id,
                StatTimeseries.segment_id == anomaly.segment_id,
                StatTimeseries.period == anomaly.period,
            )
        )
    ).scalar_one_or_none()

    # baselines (subperiod_id IS NULL — 전체 기간 기준선, D-15)
    baseline = (
        await db.execute(
            select(Baseline).where(
                Baseline.commodity_id == anomaly.commodity_id,
                Baseline.segment_id == anomaly.segment_id,
                Baseline.subperiod_id.is_(None),
            )
        )
    ).scalar_one_or_none()

    if not stat_ts or not baseline:
        raise APIError(
            "API-ANO-002",
            "이상 탐지와 연관된 통계 시계열 또는 기준선 데이터가 없습니다.",
            context={
                "anomaly_id": anomaly_id,
                "has_stat_ts": stat_ts is not None,
                "has_baseline": baseline is not None,
            },
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )

    # asymmetry_results
    asymmetry = (
        await db.execute(
            select(AsymmetryResult).where(
                AsymmetryResult.commodity_id == anomaly.commodity_id,
                AsymmetryResult.segment_id == anomaly.segment_id,
            )
        )
    ).scalar_one_or_none()

    # cointegration_results (stat_metrics.cointegrated·model_type 출처)
    cointegration = (
        await db.execute(
            select(CointegrationResult).where(
                CointegrationResult.commodity_id == anomaly.commodity_id,
                CointegrationResult.segment_id == anomaly.segment_id,
            )
        )
    ).scalar_one_or_none()

    # ml_scores (조인 키: commodity_id, segment_id, period — FK 없음)
    ml_score = (
        await db.execute(
            select(MLScore).where(
                MLScore.commodity_id == anomaly.commodity_id,
                MLScore.segment_id == anomaly.segment_id,
                MLScore.period == anomaly.period,
            )
        )
    ).scalar_one_or_none()

    # subperiod_index
    subperiod_index: int | None = None
    if anomaly.subperiod_id:
        sp = await db.get(Subperiod, anomaly.subperiod_id)
        if sp:
            subperiod_index = sp.subperiod_index

    # breakpoints.bp_dates (D-16: baselines 아님)
    bp_row = (
        await db.execute(
            select(Breakpoint).where(
                Breakpoint.commodity_id == anomaly.commodity_id,
                Breakpoint.segment_id == anomaly.segment_id,
            )
        )
    ).scalar_one_or_none()
    bp_dates: list[str] = []
    if bp_row and bp_row.bp_dates:
        bp_dates = [d.strftime("%Y-%m") for d in bp_row.bp_dates]

    # commodity name_kr
    commodity = (
        await db.execute(
            select(Commodity).where(Commodity.commodity_id == anomaly.commodity_id)
        )
    ).scalar_one_or_none()
    commodity_name_kr = commodity.name_kr if commodity else anomaly.commodity_id

    # ── StatMetrics ────────────────────────────────────────────────────────
    model_type = (
        (cointegration.model_type if cointegration else None) or baseline.model_type
    )
    stat_metrics = StatMetrics(
        transmission_rate=_to_float(anomaly.transmission_rate),
        rolling_mean=_to_float(stat_ts.rolling_mean),
        zscore=_to_float(stat_ts.zscore),
        zscore_warning=anomaly.zscore_warning,
        zscore_alert=anomaly.zscore_alert,
        zscore_threshold_warning=settings.zscore_warning,
        zscore_threshold_alert=settings.zscore_alert,
        q1=_to_float(stat_ts.q1),
        q3=_to_float(stat_ts.q3),
        iqr_lower=_to_float(stat_ts.iqr_lower),
        iqr_upper=_to_float(stat_ts.iqr_upper),
        iqr_outlier=anomaly.iqr_outlier,
        over_transmission=anomaly.over_transmission,
        under_transmission=anomaly.under_transmission,
        normal_lag=anomaly.normal_lag,
        actual_lag=anomaly.actual_lag,
        direction_reversal=anomaly.direction_reversal,
        lag_deviation=anomaly.lag_deviation,
        pattern1_flag_type=anomaly.pattern1_flag_type,
        ect_or_spread=_to_float(stat_ts.ect_or_spread),
        ect_type=stat_ts.ect_type,
        spread_n3=_to_float(anomaly.spread_n3_value),
        alpha_plus=_to_float(asymmetry.alpha_plus) if asymmetry else None,
        alpha_minus=_to_float(asymmetry.alpha_minus) if asymmetry else None,
        wald_pvalue=_to_float(asymmetry.wald_pvalue) if asymmetry else None,
        asymmetry_significant=asymmetry.asymmetry_significant if asymmetry else None,
        rocket_feather_direction=(
            asymmetry.rocket_feather_direction if asymmetry else None
        ),
        model_type=model_type,
        cointegrated=cointegration.cointegrated if cointegration else None,
        subperiod_index=subperiod_index,
        bp_dates=bp_dates,
    )

    # ── MLSummary ──────────────────────────────────────────────────────────
    ml_summary = MLSummary(
        ml_vote=anomaly.ml_vote,
        ml_detected=anomaly.ml_detected,
        if_anomaly=anomaly.if_anomaly,
        if_score=_to_float(ml_score.if_score) if ml_score else None,
        if_percentile=_to_float(ml_score.if_percentile) if ml_score else None,
        lof_anomaly=anomaly.lof_anomaly,
        lof_score=_to_float(ml_score.lof_score) if ml_score else None,
        lof_percentile=_to_float(ml_score.lof_percentile) if ml_score else None,
        svm_anomaly=anomaly.svm_anomaly,
        svm_score=_to_float(ml_score.svm_score) if ml_score else None,
        svm_percentile=_to_float(ml_score.svm_percentile) if ml_score else None,
    )

    judgment_path = _build_judgment_path(anomaly, stat_ts, ml_summary, settings)

    return AnomalyDetailResponse(
        anomaly_id=anomaly.id,
        commodity_id=anomaly.commodity_id,
        commodity_name_kr=commodity_name_kr,
        segment_id=anomaly.segment_id,
        segment_label_kr=segment.label_kr,
        period=anomaly.period.strftime("%Y-%m"),
        primary_pattern=anomaly.primary_pattern,
        pattern_types=list(anomaly.pattern_types),
        confidence_grade=anomaly.confidence_grade,
        is_new=anomaly.is_new,
        stat_metrics=stat_metrics,
        ml_summary=ml_summary,
        judgment_path=judgment_path,
    )


async def get_stat_series(
    db: AsyncSession,
    anomaly_id: int,
    metric: str,
    from_: str | None,
    to_: str | None,
    granularity: str,
) -> StatSeriesResponse:
    """GET /anomalies/{id}/stat-series — metric 4종 시계열.

    metric 검증:
    - iqr/asymmetry → 400 SNAPSHOT_METRIC_ON_SERIES
    - 허용 목록 외   → 400 INVALID_METRIC
    """
    if metric in _SNAPSHOT_ONLY:
        raise APIError(
            "API-MET-002",
            "해당 지표는 /stat-snapshot 엔드포인트를 사용하십시오.",
            context={"metric": metric},
            http_status=400,
            public_code="SNAPSHOT_METRIC_ON_SERIES",
        )
    if metric not in _SERIES_METRICS:
        raise APIError(
            "API-MET-001",
            f"지원하지 않는 metric입니다: {metric!r}. "
            f"허용값: {', '.join(sorted(_SERIES_METRICS))}",
            context={"metric": metric},
            http_status=400,
            public_code="INVALID_METRIC",
        )

    anomaly, _ = await _get_anomaly_and_segment(db, anomaly_id)

    # from/to 날짜 처리
    if from_ is not None and to_ is not None:
        from_date = _parse_yyyymm(from_)
        to_date = _parse_yyyymm(to_)
        if from_date > to_date:
            raise APIError(
                "API-STR-002",
                "from이 to보다 이후일 수 없습니다.",
                context={"from": from_, "to": to_},
                http_status=400,
                public_code="INVALID_DATE_RANGE",
            )
    elif from_ is not None:
        from_date = _parse_yyyymm(from_)
        to_date = None
    elif to_ is not None:
        from_date = None
        to_date = _parse_yyyymm(to_)
    else:
        from_date = None
        to_date = None

    # 기본값: commodity.analysis_start ~ 최신 period
    if from_date is None:
        commodity = (
            await db.execute(
                select(Commodity).where(Commodity.commodity_id == anomaly.commodity_id)
            )
        ).scalar_one_or_none()
        if commodity and commodity.analysis_start:
            from_date = commodity.analysis_start
        else:
            min_result = await db.execute(
                select(func.min(StatTimeseries.period)).where(
                    StatTimeseries.commodity_id == anomaly.commodity_id,
                    StatTimeseries.segment_id == anomaly.segment_id,
                )
            )
            from_date = min_result.scalar()

    if to_date is None:
        max_result = await db.execute(
            select(func.max(StatTimeseries.period)).where(
                StatTimeseries.commodity_id == anomaly.commodity_id,
                StatTimeseries.segment_id == anomaly.segment_id,
            )
        )
        to_date = max_result.scalar()

    # stat_timeseries 조회
    stmt = (
        select(StatTimeseries)
        .where(
            StatTimeseries.commodity_id == anomaly.commodity_id,
            StatTimeseries.segment_id == anomaly.segment_id,
        )
        .order_by(StatTimeseries.period)
    )
    if from_date:
        stmt = stmt.where(StatTimeseries.period >= from_date)
    if to_date:
        stmt = stmt.where(StatTimeseries.period <= to_date)

    rows: list[StatTimeseries] = list((await db.execute(stmt)).scalars().all())

    if not rows:
        raise APIError(
            "API-ANO-002",
            "해당 이상 탐지와 연관된 통계 시계열 데이터가 없습니다.",
            context={"anomaly_id": anomaly_id},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )

    # breakpoints.bp_dates (metric=breakpoints 시 is_breakpoint 마킹)
    bp_dates_set: set[date] = set()
    if metric == "breakpoints":
        bp_row = (
            await db.execute(
                select(Breakpoint).where(
                    Breakpoint.commodity_id == anomaly.commodity_id,
                    Breakpoint.segment_id == anomaly.segment_id,
                )
            )
        ).scalar_one_or_none()
        if bp_row and bp_row.bp_dates:
            bp_dates_set = set(bp_row.bp_dates)

    points = _rows_to_series_points(rows, metric, granularity, bp_dates_set)

    actual_from = points[0].period if points else (from_ or "")
    actual_to = points[-1].period if points else (to_ or "")
    requested_from = from_ or actual_from
    requested_to = to_ or actual_to

    return StatSeriesResponse(
        anomaly_id=anomaly.id,
        commodity_id=anomaly.commodity_id,
        segment_id=anomaly.segment_id,
        metric=metric,
        highlight_period=anomaly.period.strftime("%Y-%m"),
        requested_from=requested_from,
        requested_to=requested_to,
        actual_from=actual_from,
        actual_to=actual_to,
        granularity=granularity,
        total_points=len(points),
        data=points,
    )


async def get_stat_snapshot_iqr(
    db: AsyncSession,
    anomaly_id: int,
    settings: Settings,
) -> StatSnapshotIQRResponse:
    """GET /anomalies/{id}/stat-snapshot?metric=iqr — IQR 박스플롯 스냅샷."""
    anomaly, _ = await _get_anomaly_and_segment(db, anomaly_id)

    stat_ts = (
        await db.execute(
            select(StatTimeseries).where(
                StatTimeseries.commodity_id == anomaly.commodity_id,
                StatTimeseries.segment_id == anomaly.segment_id,
                StatTimeseries.period == anomaly.period,
            )
        )
    ).scalar_one_or_none()

    if not stat_ts:
        raise APIError(
            "API-ANO-002",
            "IQR 스냅샷에 필요한 통계 시계열 데이터가 없습니다.",
            context={"anomaly_id": anomaly_id},
            http_status=500,
            public_code="PIPELINE_DATA_MISSING",
        )

    return StatSnapshotIQRResponse(
        anomaly_id=anomaly.id,
        metric="iqr",
        period=anomaly.period.strftime("%Y-%m"),
        q1=_to_float(stat_ts.q1),
        median=_to_float(stat_ts.rolling_mean),
        q3=_to_float(stat_ts.q3),
        iqr_lower=_to_float(stat_ts.iqr_lower),
        iqr_upper=_to_float(stat_ts.iqr_upper),
        current_value=_to_float(anomaly.transmission_rate),
        window_months=settings.rolling_window,
    )


async def get_stat_snapshot_asymmetry(
    db: AsyncSession,
    anomaly_id: int,
) -> StatSnapshotAsymmetryResponse:
    """GET /anomalies/{id}/stat-snapshot?metric=asymmetry — 비대칭 히스토그램 스냅샷.

    up_samples/down_samples: upstream_pct > 0 / < 0 월의 transmission_rate 목록.
    """
    anomaly, _ = await _get_anomaly_and_segment(db, anomaly_id)

    asymmetry = (
        await db.execute(
            select(AsymmetryResult).where(
                AsymmetryResult.commodity_id == anomaly.commodity_id,
                AsymmetryResult.segment_id == anomaly.segment_id,
            )
        )
    ).scalar_one_or_none()

    # stat_timeseries 전체 (국면 구분 집계)
    ts_rows: list[StatTimeseries] = list(
        (
            await db.execute(
                select(StatTimeseries)
                .where(
                    StatTimeseries.commodity_id == anomaly.commodity_id,
                    StatTimeseries.segment_id == anomaly.segment_id,
                    StatTimeseries.transmission_rate.is_not(None),
                    StatTimeseries.upstream_pct.is_not(None),
                )
                .order_by(StatTimeseries.period)
            )
        )
        .scalars()
        .all()
    )

    up_samples: list[float] = []
    down_samples: list[float] = []
    for row in ts_rows:
        up_pct = _to_float(row.upstream_pct)
        tr = _to_float(row.transmission_rate)
        if up_pct is None or tr is None:
            continue
        if up_pct > 0:
            up_samples.append(tr)
        elif up_pct < 0:
            down_samples.append(tr)

    return StatSnapshotAsymmetryResponse(
        anomaly_id=anomaly.id,
        metric="asymmetry",
        model_type=asymmetry.model_type if asymmetry else None,
        up_samples=up_samples,
        down_samples=down_samples,
        alpha_plus=_to_float(asymmetry.alpha_plus) if asymmetry else None,
        alpha_minus=_to_float(asymmetry.alpha_minus) if asymmetry else None,
        wald_pvalue=_to_float(asymmetry.wald_pvalue) if asymmetry else None,
        asymmetry_significant=asymmetry.asymmetry_significant if asymmetry else None,
    )


async def get_irf(
    db: AsyncSession,
    anomaly_id: int,
    include_subperiods: bool,
) -> IRFResponse:
    """GET /anomalies/{id}/irf — 전체 기간 + 하위 기간별 IRF 곡선.

    scope 생성 규칙:
    - subperiod_id IS NULL → scope='full'
    - subperiod_id NOT NULL → scope='subperiod', subperiods 테이블 JOIN으로 label 생성.
    """
    anomaly, _ = await _get_anomaly_and_segment(db, anomaly_id)

    # 전체 irf_data 조회 (subperiod_id NULL + NOT NULL)
    stmt = (
        select(IRFData)
        .where(
            IRFData.commodity_id == anomaly.commodity_id,
            IRFData.segment_id == anomaly.segment_id,
        )
        .order_by(IRFData.subperiod_id.asc().nullsfirst(), IRFData.horizon)
    )
    if not include_subperiods:
        stmt = stmt.where(IRFData.subperiod_id.is_(None))

    all_irf: list[IRFData] = list((await db.execute(stmt)).scalars().all())

    # subperiod_id 목록 수집 → subperiods 테이블 조회
    subperiod_ids = {r.subperiod_id for r in all_irf if r.subperiod_id is not None}
    subperiods_map: dict[int, Subperiod] = {}
    if subperiod_ids:
        sp_rows = (
            await db.execute(
                select(Subperiod).where(Subperiod.id.in_(subperiod_ids))
            )
        ).scalars().all()
        subperiods_map = {sp.id: sp for sp in sp_rows}

    # baselines (전체 기간) — estimation_start/end 출처
    baseline = (
        await db.execute(
            select(Baseline).where(
                Baseline.commodity_id == anomaly.commodity_id,
                Baseline.segment_id == anomaly.segment_id,
                Baseline.subperiod_id.is_(None),
            )
        )
    ).scalar_one_or_none()

    # IRFData를 scope 단위로 그룹화 (subperiod_id 기준)
    def sp_key(r: IRFData) -> int | None:
        return r.subperiod_id

    sorted_irf = sorted(all_irf, key=lambda r: (r.subperiod_id is not None, r.subperiod_id or 0, r.horizon))

    curves: list[IRFCurve] = []
    grouped: dict[int | None, list[IRFData]] = {}
    for row in sorted_irf:
        grouped.setdefault(row.subperiod_id, []).append(row)

    for sp_id, irf_rows in grouped.items():
        # peak from horizon=0 row
        peak_row = next((r for r in irf_rows if r.horizon == 0), None)
        peak_horizon = peak_row.irf_peak_horizon if peak_row else None
        peak_magnitude = _to_float(peak_row.irf_peak_magnitude) if peak_row else None

        data_points = [
            IRFDataPoint(
                horizon=r.horizon,
                irf_downstream=_to_float(r.irf_downstream),
                irf_lower_ci=_to_float(r.irf_lower_ci),
                irf_upper_ci=_to_float(r.irf_upper_ci),
            )
            for r in irf_rows
        ]

        if sp_id is None:
            # 전체 기간
            est_start = _to_yyyymm(baseline.estimation_start) if baseline else None
            est_end = _to_yyyymm(baseline.estimation_end) if baseline else None
            curves.append(IRFCurve(
                scope="full",
                label="전체 기간",
                estimation_start=est_start,
                estimation_end=est_end,
                peak_horizon=peak_horizon,
                peak_magnitude=peak_magnitude,
                data=data_points,
            ))
        else:
            sp = subperiods_map.get(sp_id)
            if sp:
                label = (
                    f"{sp.period_start.strftime('%Y-%m')} ~ "
                    f"{sp.period_end.strftime('%Y-%m')}"
                )
                est_start = sp.period_start.strftime("%Y-%m")
                est_end = sp.period_end.strftime("%Y-%m")
                curves.append(IRFCurve(
                    scope="subperiod",
                    subperiod_index=sp.subperiod_index,
                    label=label,
                    estimation_start=est_start,
                    estimation_end=est_end,
                    peak_horizon=peak_horizon,
                    peak_magnitude=peak_magnitude,
                    data=data_points,
                ))

    return IRFResponse(
        commodity_id=anomaly.commodity_id,
        segment_id=anomaly.segment_id,
        irfs=curves,
    )


async def get_ml_map(
    db: AsyncSession,
    anomaly_id: int,
    model: str,
    projection_method: str,
) -> MLMapResponse:
    """GET /anomalies/{id}/ml-map — ML 결과맵 2D 투영 데이터.

    ml_projections 미산출 시 → 404 ML_MAP_NOT_READY (API-ANO-003).
    is_highlight: DB 값 우선, NULL이면 anomaly.period 와 일치 여부로 대체.
    """
    anomaly, _ = await _get_anomaly_and_segment(db, anomaly_id)

    proj_rows: list[MLProjection] = list(
        (
            await db.execute(
                select(MLProjection)
                .where(
                    MLProjection.commodity_id == anomaly.commodity_id,
                    MLProjection.segment_id == anomaly.segment_id,
                    MLProjection.model_name == model,
                    MLProjection.projection_method == projection_method,
                )
                .order_by(MLProjection.period)
            )
        )
        .scalars()
        .all()
    )

    if not proj_rows:
        raise APIError(
            "API-ANO-003",
            "ML 결과맵 데이터가 아직 산출되지 않았습니다.",
            context={
                "anomaly_id": anomaly_id,
                "model": model,
                "projection_method": projection_method,
            },
            http_status=404,
            public_code="ML_MAP_NOT_READY",
        )

    anomaly_period = anomaly.period
    x_label = proj_rows[0].x_label or "PC1"
    y_label = proj_rows[0].y_label or "PC2"

    points: list[MLMapPoint] = []
    for row in proj_rows:
        is_highlight = (
            bool(row.is_highlight)
            if row.is_highlight is not None
            else (row.period == anomaly_period)
        )
        points.append(MLMapPoint(
            period=row.period.strftime("%Y-%m"),
            x_value=_to_float(row.x_value),
            y_value=_to_float(row.y_value),
            anomaly_score=_to_float(row.anomaly_score),
            is_anomaly=bool(row.is_anomaly) if row.is_anomaly is not None else False,
            is_highlight=is_highlight,
        ))

    return MLMapResponse(
        anomaly_id=anomaly.id,
        commodity_id=anomaly.commodity_id,
        segment_id=anomaly.segment_id,
        model=model,
        projection_method=projection_method,
        x_label=x_label,
        y_label=y_label,
        total_points=len(points),
        points=points,
    )
