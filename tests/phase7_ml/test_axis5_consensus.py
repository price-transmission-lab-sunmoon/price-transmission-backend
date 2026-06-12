"""축 5 — 합의 기반 지표(CTA + ASC + P_stat + P_ml) 산출."""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import (
    EXTERNAL_SHOCKS,
    get_applicable_shocks,
    is_date_in_shock_windows,
    load_cross_val,
    load_predictions,
    get_ml_segments,
    log_eval,
)


def compute_cta(cv_df):
    """CTA = |stat ∩ ml| / |stat ∪ ml|"""
    stat = cv_df["stat_detected"].values
    ml = cv_df["ml_detected"].values

    intersection = (stat & ml).sum()
    union = (stat | ml).sum()

    if union == 0:
        return np.nan
    return intersection / union


def compute_asc(cv_df, shocks):
    """ASC = 합의 시점 중 충격 윈도우 내 비율."""
    # stat + ml 동시 탐지 시점
    consensus = cv_df[cv_df["stat_detected"] & cv_df["ml_detected"]]
    n_consensus = len(consensus)

    if n_consensus == 0:
        return np.nan, 0

    # 충격 윈도우 내 합의 건수
    in_shock = 0
    for _, row in consensus.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    asc = in_shock / n_consensus
    return asc, n_consensus


def compute_p_stat(cv_df, shocks):
    """P_stat = 통계 탐지 시점 중 충격 윈도우 내 비율."""
    stat_detected = cv_df[cv_df["stat_detected"] == True]
    n_stat = len(stat_detected)

    if n_stat == 0:
        return np.nan, 0

    in_shock = 0
    for _, row in stat_detected.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    return in_shock / n_stat, n_stat


def compute_p_ml(cv_df, pred_df, shocks):
    """P_ml = ML 탐지 시점 중 충격 윈도우 내 비율. predictions CSV 기준 산출."""
    ml_detected = pred_df[pred_df["ml_detected"] == True]
    n_ml = len(ml_detected)

    if n_ml == 0:
        return np.nan, 0

    in_shock = 0
    for _, row in ml_detected.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    return in_shock / n_ml, n_ml


def compute_esr_stat(cv_df, shocks):
    """ESR_stat — 보조 지표 (충격 윈도우 내 통계 탐지 1건+ → 회수 비율)."""
    n_shocks = len(shocks)
    if n_shocks == 0:
        return np.nan

    recalled = 0
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        window = cv_df[
            (cv_df["date"] >= s_start) & (cv_df["date"] <= s_end)
        ]
        if window["stat_detected"].any():
            recalled += 1

    return recalled / n_shocks


def compute_esr_ml(pred_df, shocks):
    """ESR_ml — 보조 지표 (충격 윈도우 내 ML 탐지 1건+ → 회수 비율)."""
    n_shocks = len(shocks)
    if n_shocks == 0:
        return np.nan

    recalled = 0
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        window = pred_df[
            (pred_df["date"] >= s_start) & (pred_df["date"] <= s_end)
        ]
        if window["ml_detected"].any():
            recalled += 1

    return recalled / n_shocks


def run_axis5(data_dir, ml_dir):
    segments = get_ml_segments(data_dir)
    log_eval("축 5 (CTA + ASC + P_stat + P_ml) 시작")

    all_results = []

    for cid, seg in segments:
        cv = load_cross_val(ml_dir, cid, seg)
        pred = load_predictions(ml_dir, cid, seg)
        shocks = get_applicable_shocks(data_dir, cid, seg)
        n_shocks = len(shocks)

        cta = compute_cta(cv)
        asc, n_consensus = compute_asc(cv, shocks)

        p_stat, n_stat_detected = compute_p_stat(cv, shocks)
        p_ml, n_ml_detected = compute_p_ml(cv, pred, shocks)

        esr_stat = compute_esr_stat(cv, shocks)
        esr_ml = compute_esr_ml(pred, shocks)

        # 핵심 가설: ASC > max(P_stat, P_ml)
        if (not np.isnan(asc) and not np.isnan(p_stat) and not np.isnan(p_ml)):
            hypothesis_holds = asc > max(p_stat, p_ml)
        else:
            hypothesis_holds = None

        result = {
            "commodity_id": cid,
            "segment": seg,
            "cta": round(cta, 4) if not np.isnan(cta) else np.nan,
            "asc": round(asc, 4) if not np.isnan(asc) else np.nan,
            "n_consensus": n_consensus,
            "p_stat": round(p_stat, 4) if not np.isnan(p_stat) else np.nan,
            "p_ml": round(p_ml, 4) if not np.isnan(p_ml) else np.nan,
            "n_stat_detected": n_stat_detected,
            "n_ml_detected": n_ml_detected,
            "esr_stat": round(esr_stat, 4) if not np.isnan(esr_stat) else np.nan,
            "esr_ml": round(esr_ml, 4) if not np.isnan(esr_ml) else np.nan,
            "n_shocks": n_shocks,
            "hypothesis_holds": hypothesis_holds,
        }
        all_results.append(result)

        hyp_str = "O" if hypothesis_holds else ("X" if hypothesis_holds is False else "-")
        log_eval(
            f"  {cid:12s} {seg}: "
            f"CTA={result['cta']}, ASC={result['asc']}, "
            f"P_stat={result['p_stat']}, P_ml={result['p_ml']}, "
            f"ESR_stat={result['esr_stat']}, ESR_ml={result['esr_ml']}, "
            f"ASC>max(P)={hyp_str}"
        )

    log_eval("축 5 완료")
    return all_results


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    run_axis5(DATA_DIR, ML_DIR)