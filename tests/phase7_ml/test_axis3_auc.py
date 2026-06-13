"""축 3: 통계-ML 일관성 AUC(보조 지표) 산출."""

import sys
import os
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import (
    load_predictions,
    load_cross_val,
    get_ml_segments,
    log_eval,
)


def compute_auc_segment(pred_df, cv_df):
    """단일 품목x구간의 모델별 + 앙상블 AUC와 ROC curve를 산출한다."""
    merged = pred_df.merge(
        cv_df[["date", "stat_detected"]], on="date", how="inner"
    )

    y_true = merged["stat_detected"].astype(int).values

    # 양쪽 클래스가 모두 존재해야 AUC 산출 가능
    if len(np.unique(y_true)) < 2:
        return {
            "auc_if": np.nan, "auc_lof": np.nan,
            "auc_svm": np.nan, "auc_ensemble": np.nan,
            "roc_curves": {},
        }

    # 부호 반전: "높을수록 이상"으로 통일
    scores_if = -merged["if_score"].values
    scores_lof = -merged["lof_score"].values
    scores_svm = -merged["svm_score"].values

    # 앙상블: 3종 Min-Max 정규화 평균 (이산 count 대비 ROC 곡선이 연속형)
    def minmax_norm(arr):
        rng = arr.max() - arr.min()
        if rng == 0:
            return np.zeros_like(arr)
        return (arr - arr.min()) / rng

    scores_ensemble = (
        minmax_norm(scores_if) + minmax_norm(scores_lof) + minmax_norm(scores_svm)
    ) / 3

    results = {}
    roc_curves = {}
    for name, scores in [("auc_if", scores_if), ("auc_lof", scores_lof),
                         ("auc_svm", scores_svm), ("auc_ensemble", scores_ensemble)]:
        try:
            auc = roc_auc_score(y_true, scores)
            results[name] = round(auc, 4)
            fpr, tpr, _ = roc_curve(y_true, scores)
            roc_curves[name] = (fpr.tolist(), tpr.tolist())
        except ValueError:
            results[name] = np.nan
            roc_curves[name] = ([], [])

    results["roc_curves"] = roc_curves
    return results


def interpret_auc(auc):
    if np.isnan(auc):
        return "산출 불가"
    if auc >= 0.95:
        return "독립성 의심"
    if auc >= 0.70:
        return "이상적 (독립성+일관성)"
    if auc >= 0.50:
        return "일관성 부족"
    return "역방향"


def run_axis3(data_dir, ml_dir):
    segments = get_ml_segments(data_dir)
    log_eval("축 3 (AUC) 시작")

    all_results = []

    for cid, seg in segments:
        pred = load_predictions(ml_dir, cid, seg)
        cv = load_cross_val(ml_dir, cid, seg)
        auc = compute_auc_segment(pred, cv)

        result = {"commodity_id": cid, "segment": seg, **auc}
        all_results.append(result)

        interp = interpret_auc(auc["auc_ensemble"])
        log_eval(
            f"  {cid:12s} {seg}: "
            f"IF={auc['auc_if']}, LOF={auc['auc_lof']}, "
            f"SVM={auc['auc_svm']}, ensemble={auc['auc_ensemble']} ({interp})"
        )

    auc_df = pd.DataFrame(all_results)
    log_eval(
        f"축 3 완료. 평균 AUC: "
        f"IF={auc_df['auc_if'].mean():.4f}, "
        f"LOF={auc_df['auc_lof'].mean():.4f}, "
        f"SVM={auc_df['auc_svm'].mean():.4f}, "
        f"ensemble={auc_df['auc_ensemble'].mean():.4f}"
    )

    return all_results


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    run_axis3(DATA_DIR, ML_DIR)