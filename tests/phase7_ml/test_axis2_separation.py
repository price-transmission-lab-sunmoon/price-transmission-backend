"""축 2: 이상 점수 분리도(Separation Ratio) 산출."""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import load_predictions, get_ml_segments, log_eval


def compute_separation_ratio(scores_anomaly, scores_normal):
    if len(scores_anomaly) < 2 or len(scores_normal) < 2:
        return np.nan

    med_a = np.median(scores_anomaly)
    med_n = np.median(scores_normal)

    iqr_a = np.percentile(scores_anomaly, 75) - np.percentile(scores_anomaly, 25)
    iqr_n = np.percentile(scores_normal, 75) - np.percentile(scores_normal, 25)

    mean_iqr = (iqr_a + iqr_n) / 2
    if mean_iqr < 1e-10:
        return np.nan

    return abs(med_a - med_n) / mean_iqr


def compute_separation_segment(pred_df):
    anomaly = pred_df[pred_df["ml_detected"] == True]
    normal = pred_df[pred_df["ml_detected"] == False]

    results = {}
    for model, col in [("IF", "if_score"), ("LOF", "lof_score"), ("SVM", "svm_score")]:
        sr = compute_separation_ratio(
            anomaly[col].dropna().values,
            normal[col].dropna().values,
        )
        results[f"sr_{model.lower()}"] = round(sr, 3) if not np.isnan(sr) else np.nan

    return results


def run_axis2(data_dir, ml_dir):
    segments = get_ml_segments(data_dir)
    log_eval("축 2 (분리도) 시작")

    all_results = []

    for cid, seg in segments:
        pred = load_predictions(ml_dir, cid, seg)
        sr = compute_separation_segment(pred)

        result = {"commodity_id": cid, "segment": seg, **sr}
        all_results.append(result)

        log_eval(
            f"  {cid:12s} {seg}: "
            f"SR_if={sr['sr_if']}, SR_lof={sr['sr_lof']}, SR_svm={sr['sr_svm']}"
        )

    sr_df = pd.DataFrame(all_results)
    avg_if = sr_df["sr_if"].mean()
    avg_lof = sr_df["sr_lof"].mean()
    avg_svm = sr_df["sr_svm"].mean()

    log_eval(f"축 2 완료. 평균 SR: IF={avg_if:.3f}, LOF={avg_lof:.3f}, SVM={avg_svm:.3f}")

    return all_results


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    run_axis2(DATA_DIR, ML_DIR)
