"""
축 2 -- 이상 점수 분리도
=========================
역할:
  ML 모델이 이상/정상을 내적으로 얼마나 일관되게 구분하는지를
  이상 점수 분포의 분리도(Separation Ratio)로 평가한다.

  SR = |median(이상) - median(정상)| / mean(IQR_이상, IQR_정상)
    SR > 2.0: 양호, SR 1.0~2.0: 보통, SR < 1.0: 약함

입력 파일:
  - data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv

출력: 분리도 결과 dict + violin plot

위치: tests/phase7_ml/test_axis2_separation.py
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import load_predictions, get_ml_segments, log_eval


def compute_separation_ratio(scores_anomaly, scores_normal):
    """Separation Ratio를 산출한다."""
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
    """단일 품목x구간에 대해 3종 모델의 분리도를 산출한다."""
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
    """전 20개 구간에 대해 분리도를 산출한다."""
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

    # 전체 평균
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
