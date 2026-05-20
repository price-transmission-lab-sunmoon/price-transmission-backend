"""Phase 7 + Phase 7-ML 데이터 DB 적재 스크립트.

stat_timeseries, anomaly_results 테이블에 CSV 데이터를 INSERT.
실행: python load_phase7.py
"""
from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

import asyncpg
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
PHASE7_DIR = PROJECT_ROOT / "data" / "processed" / "phase7"
PHASE7_ML_DIR = PROJECT_ROOT / "data" / "processed" / "phase7_ml"

DB_URL = "postgresql://postgres:password@localhost:5432/price_transmission"


# ─── stat_timeseries ─────────────────────────────────────────────────────────

async def load_stat_timeseries(conn: asyncpg.Connection) -> int:
    print("\n[1] stat_timeseries 적재...")
    ts_dir = PHASE7_DIR / "stat_timeseries"
    files = sorted(ts_dir.glob("*_stat_timeseries.csv"))
    print(f"    파일 {len(files)}개 발견")

    await conn.execute("DELETE FROM stat_timeseries")

    total = 0
    pipeline_run_id = await conn.fetchval(
        "SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1"
    )

    for f in files:
        df = pd.read_csv(f, parse_dates=["period"])
        df["period"] = pd.to_datetime(df["period"]).dt.date
        df["pipeline_run_id"] = pipeline_run_id

        # in_stable_period: float in CSV (0.0/1.0/NaN) → bool or None
        if "in_stable_period" in df.columns:
            df["in_stable_period"] = df["in_stable_period"].apply(
                lambda x: None if pd.isna(x) else bool(x)
            )

        # in_warmup_period: bool
        df["in_warmup_period"] = df["in_warmup_period"].astype(bool)

        # numeric(12,6) max ≈ 999999.999999 — clamp overflows to None
        NUMERIC_MAX = 999999.9
        ZSCORE_MAX = 999999.9  # numeric(10,4) max ~ 999999

        # float NaN → None for asyncpg
        float_cols = [
            "transmission_rate", "upstream_pct", "downstream_pct",
            "rolling_mean", "rolling_std", "zscore", "q1", "q3", "iqr",
            "iqr_lower", "iqr_upper", "zscore_w36", "zscore_w60",
            "ect_or_spread", "spread_n2", "spread_n3", "spread_n6",
            "exchange_rate_pct", "intl_price_usd_pct",
        ]
        # ect_type: None if NaN
        if "ect_type" in df.columns:
            df["ect_type"] = df["ect_type"].apply(
                lambda x: None if pd.isna(x) else str(x)
            )

        # Build tuples directly, converting NaN→None at tuple-construction time
        # (pandas float64 columns can't store None; conversion must happen here)
        def F(val, limit=NUMERIC_MAX):
            """float NaN/Inf/over-range → None"""
            if val is None:
                return None
            try:
                f = float(val)
            except (TypeError, ValueError):
                return None
            if math.isnan(f) or math.isinf(f) or abs(f) > limit:
                return None
            return f

        def FZ(val):
            return F(val, ZSCORE_MAX)

        def B(val):
            """bool or None"""
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            return bool(val)

        def S(val):
            """str or None"""
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            return str(val)

        rows = df.to_dict("records")
        await conn.executemany(
            """
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
                $1, $2, $3,
                $4, $5, $6,
                $7, $8, $9,
                $10, $11, $12, $13, $14,
                $15, $16, $17,
                $18, $19, $20,
                $21, $22, $23,
                $24, $25,
                $26
            )
            """,
            [
                (
                    r["commodity_id"], r["segment_id"], r["period"],
                    F(r.get("transmission_rate")), F(r.get("upstream_pct")), F(r.get("downstream_pct")),
                    F(r.get("rolling_mean")), F(r.get("rolling_std")), FZ(r.get("zscore")),
                    F(r.get("q1")), F(r.get("q3")), F(r.get("iqr")), F(r.get("iqr_lower")), F(r.get("iqr_upper")),
                    bool(r["in_warmup_period"]), FZ(r.get("zscore_w36")), FZ(r.get("zscore_w60")),
                    F(r.get("ect_or_spread")), S(r.get("ect_type")), B(r.get("in_stable_period")),
                    F(r.get("spread_n2")), F(r.get("spread_n3")), F(r.get("spread_n6")),
                    F(r.get("exchange_rate_pct")), F(r.get("intl_price_usd_pct")),
                    r.get("pipeline_run_id"),
                )
                for r in rows
            ],
        )
        total += len(rows)
        print(f"    OK {f.name}: {len(rows)} rows")

    print(f"    stat_timeseries total {total} rows loaded")
    return total


# ─── anomaly_results ──────────────────────────────────────────────────────────

def _load_pattern1_dfs() -> pd.DataFrame:
    """pattern1 CSVs 합치기"""
    p1_dir = PHASE7_DIR / "pattern1"
    dfs = []
    for f in sorted(p1_dir.glob("*_pattern1.csv")):
        if "summary" in f.name:
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _load_pattern2_zscore_dfs() -> pd.DataFrame:
    """pattern2_zscore CSVs 합치기"""
    p2_dir = PHASE7_DIR / "pattern2"
    dfs = []
    for f in sorted(p2_dir.glob("*_pattern2_zscore.csv")):
        df = pd.read_csv(f, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _load_pattern3_dfs() -> pd.DataFrame:
    """pattern3 CSVs 합치기"""
    p3_dir = PHASE7_DIR / "pattern3"
    dfs = []
    for f in sorted(p3_dir.glob("*_pattern3.csv")):
        if "summary" in f.name:
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _load_grades_dfs() -> pd.DataFrame:
    """ML confidence_grades CSVs 합치기"""
    grades_dir = PHASE7_ML_DIR / "confidence_grades"
    dfs = []
    for f in sorted(grades_dir.glob("*_grades.csv")):
        df = pd.read_csv(f, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _load_ml_predictions_dfs() -> pd.DataFrame:
    """ML predictions CSVs 합치기"""
    pred_dir = PHASE7_ML_DIR / "predictions"
    dfs = []
    for f in sorted(pred_dir.glob("*_ml_predictions.csv")):
        df = pd.read_csv(f, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


async def load_anomaly_results(conn: asyncpg.Connection) -> int:
    print("\n[2] anomaly_results 적재...")

    await conn.execute("DELETE FROM anomaly_results")

    # 소스 로드
    p1 = _load_pattern1_dfs()
    p2 = _load_pattern2_zscore_dfs()
    p3 = _load_pattern3_dfs()
    grades = _load_grades_dfs()
    preds = _load_ml_predictions_dfs()

    print(f"    grades: {len(grades)}행, p1: {len(p1)}행, p2: {len(p2)}행, p3: {len(p3)}행, preds: {len(preds)}행")

    if grades.empty:
        print("    WARN grades 없음 — anomaly_results 0행")
        return 0

    pipeline_run_id = await conn.fetchval(
        "SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1"
    )

    # grades가 기준 (anomaly 이벤트 목록)
    # key: (commodity_id, segment_id, date)
    KEY = ["commodity_id", "segment_id", "date"]

    # p1 조인
    if not p1.empty:
        p1_sel = p1[["commodity_id", "segment_id", "date",
                      "direction_reversal", "lag_elapsed", "normal_lag",
                      "lag_deviation", "subperiod_id", "flag_type",
                      "upstream_pct", "downstream_pct"]].copy()
        merged = grades.merge(p1_sel, on=KEY, how="left", suffixes=("", "_p1"))
    else:
        merged = grades.copy()
        for col in ["direction_reversal", "lag_elapsed", "normal_lag", "lag_deviation",
                    "subperiod_id", "flag_type", "upstream_pct", "downstream_pct"]:
            merged[col] = None

    # p2 조인 — transmission_rate, zscore 관련
    if not p2.empty:
        p2_sel = p2[["commodity_id", "segment_id", "date",
                      "transmission_rate", "zscore",
                      "zscore_warning", "zscore_alert", "iqr_outlier",
                      "over_transmission", "under_transmission"]].copy()
        merged = merged.merge(p2_sel, on=KEY, how="left", suffixes=("", "_p2"))
    else:
        for col in ["transmission_rate", "zscore", "zscore_warning", "zscore_alert",
                    "iqr_outlier", "over_transmission", "under_transmission"]:
            merged[col] = None if col not in merged.columns else merged[col]

    # p3 조인
    if not p3.empty:
        # pattern3_n: sum of n in flags? use pattern3_flag_n3 as indicator
        p3_sel = p3[["commodity_id", "segment_id", "date", "ect_or_spread"]].copy()
        p3_sel = p3_sel.rename(columns={"ect_or_spread": "spread_n3_from_p3"})
        merged = merged.merge(p3_sel, on=KEY, how="left")
    else:
        merged["spread_n3_from_p3"] = None

    # ML predictions 조인
    if not preds.empty:
        preds_sel = preds[["commodity_id", "segment_id", "date",
                            "if_anomaly", "lof_anomaly", "svm_anomaly",
                            "ml_consensus_count"]].copy()
        preds_sel = preds_sel.rename(columns={"ml_consensus_count": "ml_vote_pred"})
        merged = merged.merge(preds_sel, on=KEY, how="left")
    else:
        for col in ["if_anomaly", "lof_anomaly", "svm_anomaly", "ml_vote_pred"]:
            merged[col] = None

    print(f"    merged: {len(merged)}행")

    def _bool(v, default=False):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return bool(v)

    def _int_or_none(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return int(v)

    def _float_or_none(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)

    def _str_or_none(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return str(v)

    records = []
    for _, row in merged.iterrows():
        # pattern_type: NaN/None → default "pattern1" (ML-only detections)
        pt_raw = row.get("pattern_type")
        if pt_raw is None or (isinstance(pt_raw, float) and pd.isna(pt_raw)):
            pattern_type = "pattern1"
        else:
            pattern_type = str(pt_raw)
            if pattern_type not in ("pattern1", "pattern2", "pattern3"):
                pattern_type = "pattern1"
        # pattern_types array
        pattern_types = [pattern_type]

        # transmission_rate: from p2 if present, else from p1 upstream/downstream
        tr = _float_or_none(row.get("transmission_rate"))

        # zscore_value
        zscore_val = _float_or_none(row.get("zscore"))

        # flags: default False if null
        direction_reversal = _bool(row.get("direction_reversal"))
        lag_deviation = _bool(row.get("lag_deviation"))
        zscore_warning = _bool(row.get("zscore_warning"))
        zscore_alert = _bool(row.get("zscore_alert"))
        iqr_outlier = _bool(row.get("iqr_outlier"))
        over_transmission = _bool(row.get("over_transmission"))
        under_transmission = _bool(row.get("under_transmission"))

        stat_detected = _bool(row.get("stat_detected"))
        ml_detected = _bool(row.get("ml_detected"))
        # ml_vote: from grades ml_consensus_count, or from preds
        ml_vote_raw = row.get("ml_consensus_count") or row.get("ml_vote_pred")
        ml_vote = _int_or_none(ml_vote_raw) or 0

        confidence_grade = str(row.get("confidence_grade", "reference") or "reference")

        # subperiod_id
        subperiod_id = _int_or_none(row.get("subperiod_id"))

        # pattern1 fields
        actual_lag = _int_or_none(row.get("lag_elapsed"))
        normal_lag = _int_or_none(row.get("normal_lag"))
        flag_type = _str_or_none(row.get("flag_type"))

        # spread_n3
        spread_n3 = _float_or_none(row.get("spread_n3_from_p3"))

        # ML model flags
        if_anomaly = None
        lof_anomaly = None
        svm_anomaly = None
        if "if_anomaly" in row.index and not pd.isna(row.get("if_anomaly")):
            if_anomaly = bool(row["if_anomaly"])
        if "lof_anomaly" in row.index and not pd.isna(row.get("lof_anomaly")):
            lof_anomaly = bool(row["lof_anomaly"])
        if "svm_anomaly" in row.index and not pd.isna(row.get("svm_anomaly")):
            svm_anomaly = bool(row["svm_anomaly"])

        records.append((
            str(row["commodity_id"]),
            str(row["segment_id"]),
            row["date"].date() if hasattr(row["date"], "date") else row["date"],
            pattern_types,          # text[]
            pattern_type,           # primary_pattern
            direction_reversal,     # bool NOT NULL
            lag_deviation,          # bool NOT NULL
            flag_type,              # pattern1_flag_type nullable
            actual_lag,             # smallint nullable
            normal_lag,             # smallint nullable
            tr,                     # transmission_rate nullable
            zscore_val,             # zscore_value nullable
            zscore_warning,         # bool NOT NULL
            zscore_alert,           # bool NOT NULL
            iqr_outlier,            # bool NOT NULL
            over_transmission,      # bool NOT NULL
            under_transmission,     # bool NOT NULL
            spread_n3,              # spread_n3_value nullable
            None,                   # pattern3_n nullable
            stat_detected,          # bool NOT NULL
            ml_detected,            # bool NOT NULL
            ml_vote,                # smallint NOT NULL
            if_anomaly,             # nullable
            lof_anomaly,            # nullable
            svm_anomaly,            # nullable
            confidence_grade,       # varchar NOT NULL
            subperiod_id,           # nullable
            False,                  # is_new
            pipeline_run_id,        # nullable
        ))

    await conn.executemany(
        """
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
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29
        )
        """,
        records,
    )

    print(f"    anomaly_results {len(records)}행 적재 완료")
    return len(records)


# ─── REFRESH MATERIALIZED VIEW ────────────────────────────────────────────────

async def refresh_views(conn: asyncpg.Connection):
    print("\n[3] Materialized View REFRESH...")
    # mv_anomaly_density_yearly 가 있을 경우
    try:
        await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_anomaly_density_yearly")
        print("    OK mv_anomaly_density_yearly refreshed")
    except Exception as e:
        try:
            await conn.execute("REFRESH MATERIALIZED VIEW mv_anomaly_density_yearly")
            print("    OK mv_anomaly_density_yearly refreshed (non-concurrent)")
        except Exception as e2:
            print(f"    WARN MV refresh 실패 (무시): {e2}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Phase 7 DB 적재")
    print("=" * 60)

    conn = await asyncpg.connect(DB_URL)
    try:
        ts_count = await load_stat_timeseries(conn)
        ar_count = await load_anomaly_results(conn)
        await refresh_views(conn)

        print("\n" + "=" * 60)
        print(f"  완료: stat_timeseries {ts_count}행, anomaly_results {ar_count}행")
        print("=" * 60)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
