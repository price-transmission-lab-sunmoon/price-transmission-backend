"""Phase 2~7-ML 통합 DB 적재 스크립트.

load_phase7.py 가 stat_timeseries, anomaly_results 만 적재한다.
이 스크립트는 그 외 Phase 2~6 + Phase 7-ML 테이블을 추가로 적재한다.

적재 대상 테이블:
  - stationarity_results       ← processed/phase2/stationarity_results.csv
  - cointegration_results      ← processed/phase3/cointegration_results.csv
  - baselines (전체 기간만)    ← processed/phase4/baseline/{cid}_{seg}_baseline.json
  - model_params (전체 기간만) ← processed/phase4/model_params/{cid}_{seg}_model.json
  - irf_data (전체 기간만)     ← processed/phase4/irf/{cid}_{seg}_irf.csv
  - granger_results            ← processed/phase5/granger_results.csv
  - subperiods                 ← processed/phase6/breakpoints/{cid}_{seg}_breakpoints.json
  - breakpoints                ← processed/phase6/breakpoints/{cid}_{seg}_breakpoints.json
  - asymmetry_results          ← processed/phase7/pattern2/{cid}_{seg}_pattern2_asymmetry.csv
  - ml_scores                  ← processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv
                                  + percentile 산출 (segment 단위, rank ascending=False)
  - ml_projections             ← processed/phase7_ml/features/{cid}_{seg}_features.csv (+ PCA)
                                  (cid, seg, period) × 3 model_name = 3행
  - raw_prices                 ← processed/merged/{cid}.csv (+ 2020=100 지수 산출)
  - data_freshness 갱신        ← baseline.json의 estimation_period_end (data_up_to)

실행: python load_pipeline_outputs.py
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from pathlib import Path

import asyncpg
import pandas as pd

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
PHASE2_DIR = DATA_DIR / "phase2"
PHASE3_DIR = DATA_DIR / "phase3"
PHASE4_DIR = DATA_DIR / "phase4"
PHASE5_DIR = DATA_DIR / "phase5"
PHASE6_DIR = DATA_DIR / "phase6"
PHASE7_DIR = DATA_DIR / "phase7"
PHASE7_ML_DIR = DATA_DIR / "phase7_ml"
MERGED_DIR = DATA_DIR / "merged"

# asyncpg는 SQLAlchemy 드라이버 접두사(+asyncpg)를 인식하지 못하므로 제거
DB_URL = (
    settings.database_url
    .replace("+asyncpg", "")
    .replace("+psycopg2", "")
    .replace("+psycopg", "")
)


def F(val):
    """float NaN/Inf → None"""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def I(val):
    """int → None safe"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return int(val)


def B(val):
    """bool → None safe"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "t")
    return bool(val)


def BF(val):
    """bool → False fallback (회신 v2 §2.2: *_anomaly null 금지)."""
    res = B(val)
    return False if res is None else res


def S(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val)


def yyyymm_to_date(s):
    """'YYYY-MM' → date(yyyy, mm, 1). 'YYYY-MM-DD'도 허용."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip()
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return pd.Timestamp(s + "-01").date()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return pd.Timestamp(s).date()
    return None


def parse_bp_dates(val) -> list | None:
    """phase6_summary.csv의 bp_dates 셀 (Python list 문자열) → [date, ...]"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s in ("[]", "", "nan"):
        return []
    # "['2013-05', '2020-11']" 형태
    try:
        items = re.findall(r"['\"]([0-9]{4}-[0-9]{2})['\"]", s)
        return [yyyymm_to_date(x) for x in items if x]
    except Exception:
        return None


async def latest_pipeline_run_id(conn: asyncpg.Connection) -> int | None:
    return await conn.fetchval(
        "SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1"
    )


async def load_stationarity(conn, run_id):
    csv_path = PHASE2_DIR / "stationarity_results.csv"
    if not csv_path.exists():
        print(f"  SKIP stationarity_results — {csv_path} 없음")
        return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    await conn.execute("DELETE FROM stationarity_results")
    rows = [
        (
            S(r["commodity_id"]),
            S(r["column"]),
            I(r["n_obs"]),
            F(r.get("level_adf_stat")), F(r.get("level_adf_pvalue")),
            I(r.get("level_adf_lags")), B(r.get("level_adf_stationary")),
            F(r.get("level_kpss_stat")), F(r.get("level_kpss_pvalue")),
            B(r.get("level_kpss_stationary")),
            S(r.get("level_judgment")), S(r.get("level_conflict_note")),
            F(r.get("diff_adf_stat")), F(r.get("diff_adf_pvalue")),
            F(r.get("diff_kpss_stat")), F(r.get("diff_kpss_pvalue")),
            S(r.get("diff_judgment")),
            I(r["integration_order"]) or 0,
            False,  # i2_flag (CSV에 없음, 기본 False)
            run_id,
        )
        for _, r in df.iterrows()
    ]
    await conn.executemany(
        """
        INSERT INTO stationarity_results (
            commodity_id, price_col, n_obs,
            level_adf_stat, level_adf_pvalue, level_adf_lags, level_adf_stationary,
            level_kpss_stat, level_kpss_pvalue, level_kpss_stationary,
            level_judgment, level_conflict_note,
            diff_adf_stat, diff_adf_pvalue, diff_kpss_stat, diff_kpss_pvalue,
            diff_judgment, integration_order, i2_flag, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20
        )
        """,
        rows,
    )
    print(f"  stationarity_results: {len(rows)}행")
    return len(rows)


async def load_cointegration(conn, run_id):
    csv_path = PHASE3_DIR / "cointegration_results.csv"
    if not csv_path.exists():
        print(f"  SKIP cointegration_results — {csv_path} 없음")
        return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    await conn.execute("DELETE FROM cointegration_results")
    rows = []
    for _, r in df.iterrows():
        # coint_tested 추정: trace_stat·eigen_stat 존재 시 True
        coint_tested = (
            r.get("trace_stat_r0") is not None
            and not pd.isna(r.get("trace_stat_r0"))
        )
        rows.append((
            S(r["commodity_id"]), S(r["segment"]),
            S(r.get("upstream")) or "", S(r.get("downstream")) or "",
            None, None, None,  # integration_orders는 stationarity에서 조회
            bool(coint_tested),
            F(r.get("trace_stat_r0")), None,  # trace_pvalue (CSV에 없음)
            F(r.get("eigen_stat_r0")), None,  # maxeig_pvalue
            None,  # coint_rank (Johansen 결과에서 추출 필요, 보류)
            B(r.get("cointegrated")),
            False,  # i2_flag
            S(r.get("model_selected")),
            None,  # granger_direction (phase5에서 채움 가능)
            run_id,
        ))
    await conn.executemany(
        """
        INSERT INTO cointegration_results (
            commodity_id, segment_id, upstream_col, downstream_col,
            upstream_integration_order, downstream_integration_order,
            integration_order_match, coint_tested,
            trace_stat, trace_pvalue, maxeig_stat, maxeig_pvalue,
            coint_rank, cointegrated, i2_flag, model_type, granger_direction,
            pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18
        )
        """,
        rows,
    )
    print(f"  cointegration_results: {len(rows)}행")
    return len(rows)


async def load_baselines(conn, run_id):
    baseline_dir = PHASE4_DIR / "baseline"
    files = sorted(baseline_dir.glob("*_baseline.json"))
    await conn.execute("DELETE FROM baselines WHERE subperiod_id IS NULL")
    rows = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        warmup_end = yyyymm_to_date(d.get("warmup_end"))
        est_start = yyyymm_to_date(d.get("estimation_period_start"))
        est_end = yyyymm_to_date(d.get("estimation_period_end"))
        if not (warmup_end and est_start and est_end):
            continue
        rows.append((
            S(d["commodity_id"]), S(d["segment"]),
            None,  # subperiod_id NULL = 전체 기간
            I(d["normal_transmission_lag"]),
            F(d["transmission_elasticity"]),
            warmup_end, S(d["model_type"]),
            est_start, est_end, I(d["n_obs"]),
            run_id,
        ))
    await conn.executemany(
        """
        INSERT INTO baselines (
            commodity_id, segment_id, subperiod_id,
            normal_transmission_lag, transmission_elasticity,
            warmup_end, model_type,
            estimation_start, estimation_end, n_obs, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11
        )
        """,
        rows,
    )
    print(f"  baselines: {len(rows)}행")
    return len(rows)


async def load_model_params(conn, run_id):
    model_dir = PHASE4_DIR / "model_params"
    files = sorted(model_dir.glob("*_model.json"))
    await conn.execute("DELETE FROM model_params WHERE subperiod_id IS NULL")
    # baseline JSON의 estimation_period_start/end를 참조
    baseline_lookup = {}
    for f in (PHASE4_DIR / "baseline").glob("*_baseline.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        baseline_lookup[(d["commodity_id"], d["segment"])] = d

    rows = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        bl = baseline_lookup.get((d["commodity_id"], d["segment"]))
        if not bl:
            continue
        rows.append((
            S(d["commodity_id"]), S(d["segment"]), None,
            S(d["model_type"]), I(d["lag_selected"]),
            S(d.get("lag_selection_criterion", "AIC")),
            I(d["n_obs"]),
            yyyymm_to_date(bl["estimation_period_start"]),
            yyyymm_to_date(bl["estimation_period_end"]),
            B(d.get("cointegrated")),
            I(d.get("det_order")), I(d.get("coint_rank")),
            None, None, None,  # aic, bic, log_likelihood — CSV/JSON에 없음
            run_id,
        ))
    await conn.executemany(
        """
        INSERT INTO model_params (
            commodity_id, segment_id, subperiod_id,
            model_type, lag_selected, lag_criterion, n_obs,
            estimation_start, estimation_end, cointegrated,
            det_order, coint_rank, aic, bic, log_likelihood,
            pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
        )
        """,
        rows,
    )
    print(f"  model_params: {len(rows)}행")
    return len(rows)


async def load_irf_data(conn, run_id):
    irf_dir = PHASE4_DIR / "irf"
    files = sorted(irf_dir.glob("*_irf.csv"))
    await conn.execute("DELETE FROM irf_data WHERE subperiod_id IS NULL")
    rows = []
    for f in files:
        # 파일명: {cid}_{seg}_irf.csv
        stem = f.stem  # e.g. "wheat_A_irf" or "wheat_D_prime_irf"
        m = re.match(r"^(.+?)_([A-Za-z_]+?)_irf$", stem)
        if not m:
            continue
        cid, seg = m.group(1), m.group(2)
        df = pd.read_csv(f)
        for _, r in df.iterrows():
            h = I(r["horizon"])
            is_h0 = (h == 0)
            rows.append((
                cid, seg, None, h,
                F(r["irf_downstream"]) or 0.0,
                F(r.get("irf_lower_ci")), F(r.get("irf_upper_ci")),
                I(r.get("irf_peak_horizon")) if is_h0 else None,
                F(r.get("irf_peak_magnitude")) if is_h0 else None,
                run_id,
            ))
    await conn.executemany(
        """
        INSERT INTO irf_data (
            commodity_id, segment_id, subperiod_id, horizon,
            irf_downstream, irf_lower_ci, irf_upper_ci,
            irf_peak_horizon, irf_peak_magnitude, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10
        )
        """,
        rows,
    )
    print(f"  irf_data: {len(rows)}행 ({len(files)}개 파일)")
    return len(rows)


async def load_granger(conn, run_id):
    csv_path = PHASE5_DIR / "granger_results.csv"
    if not csv_path.exists():
        print(f"  SKIP granger_results — {csv_path} 없음")
        return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    await conn.execute("DELETE FROM granger_results")
    rows = [
        (
            S(r["commodity_id"]),
            S(r.get("segment", "C")) or "C",
            S(r["direction"]),
            I(r["max_lag"]) or 0,
            F(r.get("f_stat")),
            F(r.get("pvalue")),
            B(r["significant"]),
            S(r.get("confirmed_direction")),
            run_id,
        )
        for _, r in df.iterrows()
    ]
    await conn.executemany(
        """
        INSERT INTO granger_results (
            commodity_id, segment_id, direction, max_lag,
            f_stat, pvalue, significant, confirmed_direction, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9
        )
        """,
        rows,
    )
    print(f"  granger_results: {len(rows)}행")
    return len(rows)


async def load_subperiods_and_breakpoints(conn, run_id):
    bp_dir = PHASE6_DIR / "breakpoints"
    files = sorted(bp_dir.glob("*_breakpoints.json"))
    await conn.execute("DELETE FROM subperiods")
    await conn.execute("DELETE FROM breakpoints")

    # phase6_summary로 subperiod 개수 보강
    sum_csv = PHASE6_DIR / "phase6_summary.csv"
    summary = pd.read_csv(sum_csv) if sum_csv.exists() else pd.DataFrame()

    bp_rows = []
    sp_rows = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        cid, seg = d["commodity_id"], d["segment"]

        # breakpoints row
        bp_dates_raw = d.get("bai_perron_breakpoints", []) or []
        bp_dates = [yyyymm_to_date(x) for x in bp_dates_raw if x]
        chow = d.get("chow_test_points", {}) or {}
        c08 = chow.get("2008-01", {}) or {}
        c20 = chow.get("2020-01", {}) or {}
        c22 = chow.get("2022-01", {}) or {}
        bp_rows.append((
            cid, seg, bp_dates if bp_dates else None,
            F(c08.get("f_stat")), F(c08.get("pvalue")), B(c08.get("significant")),
            F(c20.get("f_stat")), F(c20.get("pvalue")), B(c20.get("significant")),
            F(c22.get("f_stat")), F(c22.get("pvalue")), B(c22.get("significant")),
            run_id,
        ))

        # subperiods: subperiod_models 폴더의 파일을 보고 구간 구성
        sp_models = sorted((PHASE6_DIR / "subperiod_models").glob(f"{cid}_{seg}_subperiod_*_model.json"))
        for sp_f in sp_models:
            sp_d = json.loads(sp_f.read_text(encoding="utf-8"))
            sp_rows.append((
                cid, seg,
                I(sp_d["subperiod_index"]),
                yyyymm_to_date(sp_d["subperiod_start"]),
                yyyymm_to_date(sp_d["subperiod_end"]),
                I(sp_d["n_obs"]),
                I(sp_d.get("merged_with_index")),
                run_id,
            ))

    await conn.executemany(
        """
        INSERT INTO breakpoints (
            commodity_id, segment_id, bp_dates,
            chow_2008_f, chow_2008_pvalue, chow_2008_sig,
            chow_2020_f, chow_2020_pvalue, chow_2020_sig,
            chow_2022_f, chow_2022_pvalue, chow_2022_sig,
            pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13
        )
        """,
        bp_rows,
    )
    if sp_rows:
        await conn.executemany(
            """
            INSERT INTO subperiods (
                commodity_id, segment_id, subperiod_index,
                period_start, period_end, n_obs, merged_with_index, pipeline_run_id
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8
            )
            """,
            sp_rows,
        )
    print(f"  breakpoints: {len(bp_rows)}행, subperiods: {len(sp_rows)}행")
    return len(bp_rows), len(sp_rows)


async def load_asymmetry(conn, run_id):
    asym_dir = PHASE7_DIR / "pattern2"
    files = sorted(asym_dir.glob("*_pattern2_asymmetry.csv"))
    await conn.execute("DELETE FROM asymmetry_results")
    rows = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
        except pd.errors.EmptyDataError:
            continue
        for _, r in df.iterrows():
            rows.append((
                S(r["commodity_id"]), S(r["segment"]),
                S(r["model_type"]),
                F(r.get("alpha_plus")), F(r.get("alpha_minus")),
                F(r.get("wald_stat")), F(r.get("wald_pvalue")),
                F(r.get("up_coef")), F(r.get("down_coef")),
                B(r.get("asymmetry_significant")) or False,
                S(r.get("rocket_feather_direction")),
                run_id,
            ))
    if not rows:
        print("  SKIP asymmetry_results — 파일 없음")
        return 0
    await conn.executemany(
        """
        INSERT INTO asymmetry_results (
            commodity_id, segment_id, model_type,
            alpha_plus, alpha_minus, wald_stat, wald_pvalue,
            up_coef, down_coef,
            asymmetry_significant, rocket_feather_direction, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12
        )
        """,
        rows,
    )
    print(f"  asymmetry_results: {len(rows)}행 ({len(files)}개 파일)")
    return len(rows)


async def load_ml_scores(conn, run_id):
    """predictions CSV → ml_scores + percentile 산출.

    회신 v2 §1.3: percentile = rank(pct=True, ascending=False) * 100, segment 단위.
    3종 score 모두 'lower = more anomalous' → 동일 방향. 높을수록 이상.
    회신 v2 §2.2: *_anomaly NaN → False 강제 (BF 사용).
    """
    pred_dir = PHASE7_ML_DIR / "predictions"
    files = sorted(pred_dir.glob("*_ml_predictions.csv"))
    await conn.execute("DELETE FROM ml_scores")

    if not files:
        print("  SKIP ml_scores — predictions 폴더 비어있음")
        return 0

    # 전 predictions 통합 후 segment 단위 percentile 산출
    dfs = []
    for f in files:
        d = pd.read_csv(f, parse_dates=["date"])
        d = d.rename(columns={"segment": "segment_id"})
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)

    grp = df.groupby(["commodity_id", "segment_id"])
    for src, dst in (
        ("if_score", "if_percentile"),
        ("lof_score", "lof_percentile"),
        ("svm_score", "svm_percentile"),
    ):
        if src in df.columns:
            df[dst] = grp[src].rank(pct=True, ascending=False) * 100
        else:
            df[dst] = None

    rows = []
    for _, r in df.iterrows():
        rows.append((
            S(r["commodity_id"]),
            S(r["segment_id"]),
            r["date"].date() if hasattr(r["date"], "date") else r["date"],
            F(r.get("if_score")), BF(r.get("if_anomaly")), F(r.get("if_percentile")),
            F(r.get("lof_score")), BF(r.get("lof_anomaly")), F(r.get("lof_percentile")),
            F(r.get("svm_score")), BF(r.get("svm_anomaly")), F(r.get("svm_percentile")),
            I(r.get("ml_consensus_count")) or 0,
            BF(r.get("ml_detected")),
            run_id,
        ))

    await conn.executemany(
        """
        INSERT INTO ml_scores (
            commodity_id, segment_id, period,
            if_score, if_anomaly, if_percentile,
            lof_score, lof_anomaly, lof_percentile,
            svm_score, svm_anomaly, svm_percentile,
            ml_vote, ml_detected, pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15
        )
        """,
        rows,
    )
    print(f"  ml_scores: {len(rows)}행 ({len(files)}개 파일) + percentile 산출")
    return len(rows)


_RAW_VALUE_COLS = [
    "intl_price_usd", "intl_price_krw", "import_price_usd",
    "exchange_rate", "ppi", "cpi", "wholesale_price",
]
# 2020=100 지수가 산출되는 컬럼들 (raw_prices 테이블의 *_idx 컬럼과 매핑)
_INDEX_COLS = {
    "intl_price_krw":  "intl_price_krw_idx",
    "import_price_usd": "import_price_idx",
    "ppi":             "ppi_idx",
    "cpi":             "cpi_idx",
    "wholesale_price": "wholesale_price_idx",
}


def _compute_2020_index(df: pd.DataFrame, value_col: str) -> pd.Series:
    """2020년 1~12월 평균=100 기준 지수 산출. 2020 데이터 없으면 NaN."""
    mask_2020 = pd.to_datetime(df["date"]).dt.year == 2020
    base = df.loc[mask_2020, value_col].mean()
    if pd.isna(base) or base == 0:
        return pd.Series([math.nan] * len(df), index=df.index)
    return df[value_col] / base * 100.0


async def load_raw_prices(conn, run_id):
    files = sorted(MERGED_DIR.glob("*.csv"))
    # all_commodities.csv 제외 — 품목별 파일만 사용
    files = [f for f in files if f.stem != "all_commodities"]
    if not files:
        print(f"  SKIP raw_prices — {MERGED_DIR} 비어있음")
        return 0
    await conn.execute("DELETE FROM raw_prices")
    total = 0
    for f in files:
        df = pd.read_csv(f, encoding="utf-8-sig", parse_dates=["date"])
        # 2020=100 지수 산출 (각 소스별)
        for val_col, idx_col in _INDEX_COLS.items():
            if val_col in df.columns:
                df[idx_col] = _compute_2020_index(df, val_col)
            else:
                df[idx_col] = math.nan

        # 누락된 source 컬럼 보충 (예: 3구간 품목 wholesale_price 없음)
        for c in _RAW_VALUE_COLS:
            if c not in df.columns:
                df[c] = math.nan

        rows = []
        for _, r in df.iterrows():
            period = r["date"].date() if hasattr(r["date"], "date") else r["date"]
            rows.append((
                S(r["commodity_id"]), period,
                F(r["intl_price_usd"]), F(r["intl_price_krw"]),
                F(r["import_price_usd"]),
                F(r["exchange_rate"]),
                F(r["ppi"]), F(r["cpi"]), F(r["wholesale_price"]),
                F(r["intl_price_krw_idx"]),
                F(r["import_price_idx"]),
                F(r["ppi_idx"]), F(r["cpi_idx"]),
                F(r["wholesale_price_idx"]),
            ))
        await conn.executemany(
            """
            INSERT INTO raw_prices (
                commodity_id, period,
                intl_price_usd, intl_price_krw, import_price_usd,
                exchange_rate, ppi, cpi, wholesale_price,
                intl_price_krw_idx, import_price_idx,
                ppi_idx, cpi_idx, wholesale_price_idx
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14
            )
            """,
            rows,
        )
        total += len(rows)
        print(f"    OK {f.stem}: {len(rows)} rows")
    print(f"  raw_prices total {total}행")
    return total


async def refresh_data_freshness(conn, run_id):
    """baseline.json의 estimation_period_end 중 최대값을 data_freshness.data_up_to로 갱신."""
    max_end = None
    for f in (PHASE4_DIR / "baseline").glob("*_baseline.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        end = yyyymm_to_date(d.get("estimation_period_end"))
        if end and (max_end is None or end > max_end):
            max_end = end
    if max_end is None:
        print("  SKIP data_freshness — baseline.json에서 estimation_period_end 추출 실패")
        return None

    # 다음 실행일은 다음 달 1일로 가정
    next_month = (pd.Timestamp(max_end) + pd.offsets.MonthBegin(1)).date()

    await conn.execute(
        """
        INSERT INTO data_freshness (data_up_to, next_run_date, pipeline_run_id)
        VALUES ($1, $2, $3)
        """,
        max_end, next_month, run_id,
    )
    print(f"  data_freshness 갱신: data_up_to={max_end}, next_run_date={next_month}")
    return max_end


_PCA_FEATURE_COLS = [
    "transmission_rate", "upstream_pct", "downstream_pct",
    "ect_or_spread", "exchange_rate_pct", "intl_price_usd_pct",
]

_MODEL_SCORE_MAP = [
    # (model_name, score_col, anomaly_col)
    ("isolation_forest", "if_score", "if_anomaly"),
    ("lof", "lof_score", "lof_anomaly"),
    ("ocsvm", "svm_score", "svm_anomaly"),
]


async def load_ml_projections(conn, run_id):
    """features CSV → PCA(n=2) → ml_projections.

    회신 v2 §6 ③: (cid, seg, period) × 3 model_name = 3행. 좌표 동일.
    x_label="PC1", y_label="PC2" 고정. projection_method="pca".
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    feat_dir = PHASE7_ML_DIR / "features"
    pred_dir = PHASE7_ML_DIR / "predictions"

    await conn.execute("DELETE FROM ml_projections")

    if not feat_dir.exists():
        print("  SKIP ml_projections — features 폴더 없음")
        return 0

    feat_files = sorted(feat_dir.glob("*_features.csv"))
    if not feat_files:
        print("  SKIP ml_projections — features 폴더 비어있음")
        return 0

    feats = []
    for f in feat_files:
        d = pd.read_csv(f, parse_dates=["date"])
        d = d.rename(columns={"segment": "segment_id"})
        feats.append(d)
    features_df = pd.concat(feats, ignore_index=True)

    predictions_df = pd.DataFrame()
    if pred_dir.exists():
        preds = []
        for f in sorted(pred_dir.glob("*_ml_predictions.csv")):
            d = pd.read_csv(f, parse_dates=["date"])
            d = d.rename(columns={"segment": "segment_id"})
            preds.append(d)
        if preds:
            predictions_df = pd.concat(preds, ignore_index=True)

    # segment 단위 PCA
    proj_rows = []
    for (cid, seg), grp in features_df.groupby(["commodity_id", "segment_id"]):
        X = grp[_PCA_FEATURE_COLS].copy()
        valid_mask = X.notna().all(axis=1)
        X_valid = X[valid_mask]
        if len(X_valid) < 2:
            continue

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_valid)
        pca = PCA(n_components=2, random_state=42)
        XY = pca.fit_transform(X_scaled)

        dates = grp.loc[valid_mask, "date"].reset_index(drop=True)
        for i, d in enumerate(dates):
            proj_rows.append({
                "commodity_id": cid,
                "segment_id": seg,
                "date": d.date() if hasattr(d, "date") else d,
                "x_value": float(XY[i, 0]),
                "y_value": float(XY[i, 1]),
            })

    if not proj_rows:
        print("  SKIP ml_projections — 유효 관측치 없음")
        return 0

    proj_df = pd.DataFrame(proj_rows)

    # predictions 머지 (없으면 score/anomaly 컬럼 비어있게 둠)
    if not predictions_df.empty:
        predictions_df["date"] = pd.to_datetime(predictions_df["date"]).dt.date
        pred_sel = predictions_df[[
            "commodity_id", "segment_id", "date",
            "if_score", "if_anomaly",
            "lof_score", "lof_anomaly",
            "svm_score", "svm_anomaly",
        ]].copy()
        proj_df = proj_df.merge(
            pred_sel, on=["commodity_id", "segment_id", "date"], how="left",
        )
    else:
        for _, score_col, anom_col in _MODEL_SCORE_MAP:
            proj_df[score_col] = None
            proj_df[anom_col] = False

    rows = []
    for _, r in proj_df.iterrows():
        base = (
            S(r["commodity_id"]),
            S(r["segment_id"]),
            r["date"],
            F(r["x_value"]),
            F(r["y_value"]),
            "PC1",  # x_label
            "PC2",  # y_label
            "pca",  # projection_method
            run_id,
        )
        for model_name, score_col, anom_col in _MODEL_SCORE_MAP:
            rows.append((
                base[0], base[1], base[2],
                model_name,
                F(r.get(score_col)),
                BF(r.get(anom_col)),
                base[3], base[4],
                base[5], base[6],
                base[7], base[8],
            ))

    await conn.executemany(
        """
        INSERT INTO ml_projections (
            commodity_id, segment_id, period,
            model_name,
            anomaly_score, is_anomaly,
            x_value, y_value,
            x_label, y_label,
            projection_method,
            pipeline_run_id
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12
        )
        """,
        rows,
    )
    print(f"  ml_projections: {len(rows)}행 ({len(proj_df)} 관측치 × 3 model)")
    return len(rows)


async def main():
    print("=" * 60)
    print("  Phase 2~7-ML 통합 DB 적재")
    print("=" * 60)

    conn = await asyncpg.connect(DB_URL)
    try:
        run_id = await latest_pipeline_run_id(conn)
        print(f"\npipeline_run_id = {run_id}\n")

        print("[Phase 2]")
        await load_stationarity(conn, run_id)

        print("\n[Phase 3]")
        await load_cointegration(conn, run_id)

        print("\n[Phase 4]")
        await load_baselines(conn, run_id)
        await load_model_params(conn, run_id)
        await load_irf_data(conn, run_id)

        print("\n[Phase 5]")
        await load_granger(conn, run_id)

        print("\n[Phase 6]")
        await load_subperiods_and_breakpoints(conn, run_id)

        print("\n[Phase 7 비대칭]")
        await load_asymmetry(conn, run_id)

        print("\n[Phase 7-ML]")
        await load_ml_scores(conn, run_id)
        await load_ml_projections(conn, run_id)

        print("\n[Raw Prices]")
        await load_raw_prices(conn, run_id)

        print("\n[data_freshness 갱신]")
        await refresh_data_freshness(conn, run_id)

        print("\n" + "=" * 60)
        print("  완료")
        print("=" * 60)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
