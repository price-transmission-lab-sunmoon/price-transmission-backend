"""Phase 7. stat_timeseries, anomaly_results 적재

입력:
  data/processed/phase7/stat_timeseries/{cid}_{seg}_stat_timeseries.csv (33개)
  data/processed/phase7/pattern1/{cid}_{seg}_pattern1.csv (33개)
  data/processed/phase7/pattern2/{cid}_{seg}_pattern2_zscore.csv (20개)
  data/processed/phase7/pattern3/{cid}_{seg}_pattern3.csv (10개)
  data/processed/phase7_ml/confidence_grades/{cid}_{seg}_grades.csv
  data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv

적재 대상:
  stat_timeseries: 전 시점 시계열 (33개 구간의 모든 월)
  anomaly_results: confidence_grade IS NOT NULL인 탐지 이벤트만
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.loader.base import append_phase_to_run, validate_period_day

logger = logging.getLogger(__name__)

_PHASE7_ROOT = Path(settings.pipeline_data_root) / "phase7"
_PHASE7_ML_ROOT = Path(settings.pipeline_data_root) / "phase7_ml"

NUMERIC_MAX = 999999.9
ZSCORE_MAX = 999999.9


def _F(val, limit: float = NUMERIC_MAX) -> float | None:
    """float NaN, Inf, 범위 초과값을 None으로 변환한다 (numeric(12,6) overflow 방지)."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f) or abs(f) > limit:
        return None
    return f


def _FZ(val) -> float | None:
    return _F(val, ZSCORE_MAX)


def _B(val) -> bool | None:
    """bool 또는 None을 반환한다. NaN이나 None이면 None을 반환한다."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return bool(val)


def _S(val) -> str | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return str(val)


def _I(val) -> int | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def load_stat_timeseries(session: AsyncSession, run_id: int) -> int:
    """phase7/stat_timeseries/*.csv를 읽어 stat_timeseries에 INSERT한다. 적재 행 수를 반환한다."""
    ts_dir = _PHASE7_ROOT / "stat_timeseries"
    files = sorted(ts_dir.glob("*_stat_timeseries.csv")) if ts_dir.exists() else []
    if not files:
        logger.warning(
            "Phase 7 stat_timeseries CSV 없음, skip",
            extra={"dir": str(ts_dir)},
        )
        return 0

    await session.execute(text("DELETE FROM stat_timeseries"))

    total = 0
    for fp in files:
        df = pd.read_csv(fp, parse_dates=["period"])
        df["period"] = pd.to_datetime(df["period"]).dt.date

        rows = []
        for _, r in df.iterrows():
            period = r["period"]
            validate_period_day(period, "stat_timeseries")

            rows.append({
                "commodity_id": str(r["commodity_id"]),
                "segment_id": str(r["segment_id"]),
                "period": period,
                "transmission_rate": _F(r.get("transmission_rate")),
                "upstream_pct": _F(r.get("upstream_pct")),
                "downstream_pct": _F(r.get("downstream_pct")),
                "rolling_mean": _F(r.get("rolling_mean")),
                "rolling_std": _F(r.get("rolling_std")),
                "zscore": _FZ(r.get("zscore")),
                "q1": _F(r.get("q1")),
                "q3": _F(r.get("q3")),
                "iqr": _F(r.get("iqr")),
                "iqr_lower": _F(r.get("iqr_lower")),
                "iqr_upper": _F(r.get("iqr_upper")),
                "in_warmup_period": bool(r["in_warmup_period"]),
                "zscore_w36": _FZ(r.get("zscore_w36")),
                "zscore_w60": _FZ(r.get("zscore_w60")),
                "ect_or_spread": _F(r.get("ect_or_spread")),
                "ect_type": _S(r.get("ect_type")),
                "in_stable_period": _B(r.get("in_stable_period")),
                "spread_n2": _F(r.get("spread_n2")),
                "spread_n3": _F(r.get("spread_n3")),
                "spread_n6": _F(r.get("spread_n6")),
                "exchange_rate_pct": _F(r.get("exchange_rate_pct")),
                "intl_price_usd_pct": _F(r.get("intl_price_usd_pct")),
                "pipeline_run_id": run_id,
            })

        if not rows:
            continue

        await session.execute(
            text("""
                INSERT INTO stat_timeseries (
                    commodity_id, segment_id, period,
                    transmission_rate, upstream_pct, downstream_pct,
                    rolling_mean, rolling_std, zscore,
                    q1, q3, iqr, iqr_lower, iqr_upper,
                    in_warmup_period, zscore_w36, zscore_w60,
                    ect_or_spread, ect_type, in_stable_period,
                    spread_n2, spread_n3, spread_n6,
                    exchange_rate_pct, intl_price_usd_pct,
                    pipeline_run_id
                ) VALUES (
                    :commodity_id, :segment_id, :period,
                    :transmission_rate, :upstream_pct, :downstream_pct,
                    :rolling_mean, :rolling_std, :zscore,
                    :q1, :q3, :iqr, :iqr_lower, :iqr_upper,
                    :in_warmup_period, :zscore_w36, :zscore_w60,
                    :ect_or_spread, :ect_type, :in_stable_period,
                    :spread_n2, :spread_n3, :spread_n6,
                    :exchange_rate_pct, :intl_price_usd_pct,
                    :pipeline_run_id
                )
            """),
            rows,
        )
        total += len(rows)

    return total


def _read_pattern_csvs(subdir: str, suffix: str) -> pd.DataFrame:
    """phase7/{subdir}/*{suffix}.csv 전체를 단일 DataFrame으로 합산."""
    pdir = _PHASE7_ROOT / subdir
    if not pdir.exists():
        return pd.DataFrame()
    dfs = []
    for fp in sorted(pdir.glob(f"*{suffix}.csv")):
        if "summary" in fp.name:
            continue
        df = pd.read_csv(fp, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _read_ml_csvs(subdir: str, suffix: str) -> pd.DataFrame:
    pdir = _PHASE7_ML_ROOT / subdir
    if not pdir.exists():
        return pd.DataFrame()
    dfs = []
    for fp in sorted(pdir.glob(f"*{suffix}.csv")):
        df = pd.read_csv(fp, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


async def load_anomaly_results(session: AsyncSession, run_id: int) -> int:
    """grades 기준으로 pattern1/2/3 + ml_predictions 머지하여 anomaly_results 적재."""
    p1 = _read_pattern_csvs("pattern1", "_pattern1")
    p2 = _read_pattern_csvs("pattern2", "_pattern2_zscore")
    p3 = _read_pattern_csvs("pattern3", "_pattern3")
    grades = _read_ml_csvs("confidence_grades", "_grades")
    preds = _read_ml_csvs("predictions", "_ml_predictions")

    if grades.empty:
        logger.warning("confidence_grades 없음, anomaly_results 0행")
        await session.execute(text("DELETE FROM anomaly_results"))
        return 0

    KEY = ["commodity_id", "segment_id", "date"]

    merged = grades.copy()

    if not p1.empty:
        p1_sel = p1[[
            "commodity_id", "segment_id", "date",
            "direction_reversal", "lag_elapsed", "normal_lag",
            "lag_deviation", "subperiod_id", "flag_type",
            "upstream_pct", "downstream_pct",
        ]].copy()
        merged = merged.merge(p1_sel, on=KEY, how="left", suffixes=("", "_p1"))
    else:
        for col in (
            "direction_reversal", "lag_elapsed", "normal_lag", "lag_deviation",
            "subperiod_id", "flag_type", "upstream_pct", "downstream_pct",
        ):
            merged[col] = None

    if not p2.empty:
        p2_sel = p2[[
            "commodity_id", "segment_id", "date",
            "transmission_rate", "zscore",
            "zscore_warning", "zscore_alert", "iqr_outlier",
            "over_transmission", "under_transmission",
        ]].copy()
        merged = merged.merge(p2_sel, on=KEY, how="left", suffixes=("", "_p2"))
    else:
        for col in (
            "transmission_rate", "zscore", "zscore_warning", "zscore_alert",
            "iqr_outlier", "over_transmission", "under_transmission",
        ):
            if col not in merged.columns:
                merged[col] = None

    if not p3.empty:
        p3_sel = p3[["commodity_id", "segment_id", "date", "ect_or_spread"]].copy()
        p3_sel = p3_sel.rename(columns={"ect_or_spread": "spread_n3_from_p3"})
        merged = merged.merge(p3_sel, on=KEY, how="left")
    else:
        merged["spread_n3_from_p3"] = None

    if not preds.empty:
        preds_sel = preds[[
            "commodity_id", "segment_id", "date",
            "if_anomaly", "lof_anomaly", "svm_anomaly", "ml_consensus_count",
        ]].copy()
        preds_sel = preds_sel.rename(columns={"ml_consensus_count": "ml_vote_pred"})
        merged = merged.merge(preds_sel, on=KEY, how="left")
    else:
        for col in ("if_anomaly", "lof_anomaly", "svm_anomaly", "ml_vote_pred"):
            merged[col] = None

    await session.execute(text("DELETE FROM anomaly_results"))

    rows = []
    for _, row in merged.iterrows():
        pt_raw = row.get("pattern_type")
        if pt_raw is None or (isinstance(pt_raw, float) and pd.isna(pt_raw)):
            pattern_type = "pattern1"
        else:
            pattern_type = str(pt_raw)
            if pattern_type not in ("pattern1", "pattern2", "pattern3"):
                pattern_type = "pattern1"

        d = row["date"]
        period = d.date() if hasattr(d, "date") else d
        validate_period_day(period, "anomaly_results")

        rows.append({
            "commodity_id": str(row["commodity_id"]),
            "segment_id": str(row["segment_id"]),
            "period": period,
            "pattern_types": [pattern_type],
            "primary_pattern": pattern_type,
            "direction_reversal": bool(_B(row.get("direction_reversal")) or False),
            "lag_deviation": bool(_B(row.get("lag_deviation")) or False),
            "pattern1_flag_type": _S(row.get("flag_type")),
            "actual_lag": _I(row.get("lag_elapsed")),
            "normal_lag": _I(row.get("normal_lag")),
            "transmission_rate": _F(row.get("transmission_rate")),
            "zscore_value": _FZ(row.get("zscore")),
            "zscore_warning": bool(_B(row.get("zscore_warning")) or False),
            "zscore_alert": bool(_B(row.get("zscore_alert")) or False),
            "iqr_outlier": bool(_B(row.get("iqr_outlier")) or False),
            "over_transmission": bool(_B(row.get("over_transmission")) or False),
            "under_transmission": bool(_B(row.get("under_transmission")) or False),
            "spread_n3_value": _F(row.get("spread_n3_from_p3")),
            "pattern3_n": None,
            "stat_detected": bool(_B(row.get("stat_detected")) or False),
            "ml_detected": bool(_B(row.get("ml_detected")) or False),
            "ml_vote": _I(row.get("ml_consensus_count") if not pd.isna(row.get("ml_consensus_count")) else row.get("ml_vote_pred")) or 0,
            "if_anomaly": bool(_B(row.get("if_anomaly")) or False),
            "lof_anomaly": bool(_B(row.get("lof_anomaly")) or False),
            "svm_anomaly": bool(_B(row.get("svm_anomaly")) or False),
            "confidence_grade": _S(row.get("confidence_grade")) or "reference",
            "subperiod_id": _I(row.get("subperiod_id")),
            "is_new": False,
            "pipeline_run_id": run_id,
        })

    if not rows:
        return 0

    await session.execute(
        text("""
            INSERT INTO anomaly_results (
                commodity_id, segment_id, period,
                pattern_types, primary_pattern,
                direction_reversal, lag_deviation,
                pattern1_flag_type, actual_lag, normal_lag,
                transmission_rate, zscore_value,
                zscore_warning, zscore_alert, iqr_outlier,
                over_transmission, under_transmission,
                spread_n3_value, pattern3_n,
                stat_detected, ml_detected, ml_vote,
                if_anomaly, lof_anomaly, svm_anomaly,
                confidence_grade, subperiod_id, is_new,
                pipeline_run_id
            ) VALUES (
                :commodity_id, :segment_id, :period,
                :pattern_types, :primary_pattern,
                :direction_reversal, :lag_deviation,
                :pattern1_flag_type, :actual_lag, :normal_lag,
                :transmission_rate, :zscore_value,
                :zscore_warning, :zscore_alert, :iqr_outlier,
                :over_transmission, :under_transmission,
                :spread_n3_value, :pattern3_n,
                :stat_detected, :ml_detected, :ml_vote,
                :if_anomaly, :lof_anomaly, :svm_anomaly,
                :confidence_grade, :subperiod_id, :is_new,
                :pipeline_run_id
            )
        """),
        rows,
    )
    return len(rows)


async def refresh_anomaly_density(session: AsyncSession) -> None:
    """mv_anomaly_density_yearly 갱신. 실패해도 트랜잭션은 유지."""
    try:
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_anomaly_density_yearly"))
    except Exception:
        try:
            await session.execute(text("REFRESH MATERIALIZED VIEW mv_anomaly_density_yearly"))
        except Exception as e:
            logger.warning(f"MV refresh 실패 (무시): {e}")


async def load_phase7(session: AsyncSession, run_id: int) -> dict[str, int]:
    """Phase 7 단일 트랜잭션: stat_timeseries 및 anomaly_results 적재."""
    try:
        ts_count = await load_stat_timeseries(session, run_id)
        ar_count = await load_anomaly_results(session, run_id)
        await refresh_anomaly_density(session)
        await session.commit()
    except Exception as e:
        await session.rollback()
        if isinstance(e, DBError):
            raise
        raise DBError(
            "DB-TX-001",
            "Phase 7 트랜잭션 롤백: stat_timeseries/anomaly_results 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    await append_phase_to_run(session, run_id, "7")
    logger.info(
        "Phase 7 완료",
        extra={
            "run_id": run_id,
            "stat_timeseries": ts_count,
            "anomaly_results": ar_count,
        },
    )
    return {"stat_timeseries": ts_count, "anomaly_results": ar_count}
