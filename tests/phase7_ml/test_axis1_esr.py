"""축 1: 외부 충격 회수율(ESR_ml) 산출."""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import (
    EXTERNAL_SHOCKS,
    get_applicable_shocks,
    load_predictions,
    get_ml_segments,
    log_eval,
)


def compute_esr_segment(pred_df, shocks):
    """단일 품목x구간의 모델별 + 앙상블 ESR을 산출한다."""
    shock_results = []

    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])

        window = pred_df[(pred_df["date"] >= s_start) & (pred_df["date"] <= s_end)]

        if_hit = window["if_anomaly"].any() if len(window) > 0 else False
        lof_hit = window["lof_anomaly"].any() if len(window) > 0 else False
        svm_hit = window["svm_anomaly"].any() if len(window) > 0 else False
        ml_hit = window["ml_detected"].any() if len(window) > 0 else False

        shock_results.append({
            "shock_id": shock["id"],
            "shock_name": shock["name"],
            "window_obs": len(window),
            "if_recall": if_hit,
            "lof_recall": lof_hit,
            "svm_recall": svm_hit,
            "ml_recall": ml_hit,
        })

    n_shocks = len(shock_results)
    if n_shocks == 0:
        return shock_results, {
            "n_shocks": 0,
            "esr_if": np.nan, "esr_lof": np.nan,
            "esr_svm": np.nan, "esr_ml": np.nan,
        }

    esr_if = sum(1 for r in shock_results if r["if_recall"]) / n_shocks
    esr_lof = sum(1 for r in shock_results if r["lof_recall"]) / n_shocks
    esr_svm = sum(1 for r in shock_results if r["svm_recall"]) / n_shocks
    esr_ml = sum(1 for r in shock_results if r["ml_recall"]) / n_shocks

    return shock_results, {
        "n_shocks": n_shocks,
        "esr_if": round(esr_if, 4),
        "esr_lof": round(esr_lof, 4),
        "esr_svm": round(esr_svm, 4),
        "esr_ml": round(esr_ml, 4),
    }


def run_axis1(data_dir, ml_dir):
    segments = get_ml_segments(data_dir)
    log_eval("축 1 (ESR) 시작")

    all_results = []

    for cid, seg in segments:
        pred = load_predictions(ml_dir, cid, seg)
        shocks = get_applicable_shocks(data_dir, cid, seg)

        shock_details, esr_summary = compute_esr_segment(pred, shocks)

        result = {
            "commodity_id": cid,
            "segment": seg,
            **esr_summary,
            "shock_details": shock_details,
        }
        all_results.append(result)

        shock_ids = [s["id"] for s in shocks]
        log_eval(
            f"  {cid:12s} {seg}: "
            f"shocks={esr_summary['n_shocks']} ({','.join(shock_ids)}), "
            f"ESR_ml={esr_summary['esr_ml']}"
        )

    total_shocks = sum(r["n_shocks"] for r in all_results)
    if total_shocks > 0:
        weighted_esr = sum(
            r["esr_ml"] * r["n_shocks"]
            for r in all_results if not np.isnan(r["esr_ml"])
        ) / total_shocks
    else:
        weighted_esr = np.nan

    log_eval(f"축 1 완료. 전체 가중 ESR_ml={weighted_esr:.4f}")

    return all_results, weighted_esr


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    results, weighted = run_axis1(DATA_DIR, ML_DIR)
