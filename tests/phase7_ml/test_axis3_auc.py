"""
축 3 -- 통계-ML 일관성 AUC (보조 지표)
=======================================
역할:
  Phase 7 통계 탐지 결과(stat_detected)를 pseudo-label로,
  ML 이상 점수를 스코어로 삼아 ROC AUC를 산출한다.
  이상적 AUC 구간: 0.70~0.90 (독립성과 일관성 공존).

  score 방향 통일: 3종 모델 전부 부호 반전하여 "높을수록 이상"으로 변환.
  앙상블 스코어: 3종 모델의 정규화된 이상 점수 평균 (연속형).

변경 이력:
  v2 (2026-05-18):
    - 앙상블 스코어를 이산형(ml_consensus_count 0~3) → 연속형(Min-Max 정규화 평균)으로 변경
    - ROC curve FPR/TPR 배열 반환 추가

입력 파일:
  - data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv
  - data/processed/phase7_ml/cross_validation/{cid}_{seg}_cross_val.csv

출력: AUC 결과 dict

위치: tests/phase7_ml/test_axis3_auc.py
"""

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
    """
    단일 품목x구간에 대해 모델별 + 앙상블 AUC를 산출한다.
    ROC curve (FPR/TPR 배열)도 함께 반환한다.

    pseudo-label: stat_detected (통계 탐지 여부)
    score: ML 이상 점수 (부호 반전하여 높을수록 이상으로 통일)

    Returns:
        dict {auc_if, auc_lof, auc_svm, auc_ensemble, roc_curves}
        roc_curves: {model_name: [(fpr, tpr), ...]} — 대시보드 ROC Curve용
    """
    # date 기준 merge
    merged = pred_df.merge(
        cv_df[["date", "stat_detected"]], on="date", how="inner"
    )

    y_true = merged["stat_detected"].astype(int).values

    # pseudo-label에 양쪽 클래스가 모두 존재해야 AUC 산출 가능
    if len(np.unique(y_true)) < 2:
        return {
            "auc_if": np.nan, "auc_lof": np.nan,
            "auc_svm": np.nan, "auc_ensemble": np.nan,
            "roc_curves": {},
        }

    # 부호 반전: 3종 모델 전부 "높을수록 이상"으로 통일
    scores_if = -merged["if_score"].values
    scores_lof = -merged["lof_score"].values
    scores_svm = -merged["svm_score"].values

    # 앙상블 스코어: 연속형 (Min-Max 정규화 후 평균)
    # 기존 ml_consensus_count(0~3 이산값)는 ROC 곡선이 계단형이 되어
    # AUC가 과소 측정되므로, 3종 모델의 연속 점수를 결합한다.
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
    """AUC 값에 대한 해석을 반환한다."""
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
    """전 20개 구간에 대해 AUC를 산출한다."""
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

    # 전체 평균
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