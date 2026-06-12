"""축 4 — 하이퍼파라미터 민감도(Stability Ratio) 산출."""

import sys
import os
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

src_path = os.path.join(os.path.dirname(__file__), "..", "..", "pipeline", "preprocessing", "Phase7")
sys.path.insert(0, src_path)
from phase7_ml_common import (
    FEATURE_COLUMNS,
    load_feature_matrix,
    preprocess_features,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import get_ml_segments, log_eval

RANDOM_STATE = 42
CONTAMINATION_VALUES = [0.05, 0.10, 0.15]
LOF_K_VALUES = [5, 10, 15, 20]
BASE_CONTAMINATION = 0.10
BASE_LOF_K = 10
ML_CONSENSUS_THRESHOLD = 2


def run_models_with_params(X_scaled, contamination=0.10, lof_k=10):
    """3종 모델 실행 후 consensus ml_detected를 반환한다."""
    if_model = IsolationForest(
        n_estimators=100, contamination=contamination, random_state=RANDOM_STATE
    )
    if_model.fit(X_scaled)
    if_labels = if_model.predict(X_scaled)

    lof_model = LocalOutlierFactor(
        n_neighbors=lof_k, contamination=contamination, novelty=False
    )
    lof_labels = lof_model.fit_predict(X_scaled)

    svm_model = OneClassSVM(kernel="rbf", nu=contamination, gamma="scale")
    svm_model.fit(X_scaled)
    svm_labels = svm_model.predict(X_scaled)

    consensus = (
        (if_labels == -1).astype(int)
        + (lof_labels == -1).astype(int)
        + (svm_labels == -1).astype(int)
    )
    ml_detected = consensus >= ML_CONSENSUS_THRESHOLD

    return ml_detected


def compute_stability_ratio(base_detected, alt_detected):
    base_set = set(np.where(base_detected)[0])
    alt_set = set(np.where(alt_detected)[0])

    if len(base_set) == 0:
        return np.nan

    overlap = len(base_set & alt_set)
    return overlap / len(base_set)


def run_sensitivity_segment(phase7_dir, cid, seg):
    """단일 품목x구간의 민감도 분석을 수행한다."""
    features_raw, dates = load_feature_matrix(phase7_dir, cid, seg)
    X_scaled, valid_index, scaler = preprocess_features(features_raw)

    base_detected = run_models_with_params(
        X_scaled, contamination=BASE_CONTAMINATION, lof_k=BASE_LOF_K
    )
    n_base = base_detected.sum()

    contam_results = []
    for c in CONTAMINATION_VALUES:
        alt_detected = run_models_with_params(X_scaled, contamination=c, lof_k=BASE_LOF_K)
        sr = compute_stability_ratio(base_detected, alt_detected)
        contam_results.append({
            "contamination": c,
            "n_detected": int(alt_detected.sum()),
            "stability_ratio": round(sr, 4) if not np.isnan(sr) else np.nan,
        })

    k_results = []
    for k in LOF_K_VALUES:
        alt_detected = run_models_with_params(
            X_scaled, contamination=BASE_CONTAMINATION, lof_k=k
        )
        sr = compute_stability_ratio(base_detected, alt_detected)
        k_results.append({
            "lof_k": k,
            "n_detected": int(alt_detected.sum()),
            "stability_ratio": round(sr, 4) if not np.isnan(sr) else np.nan,
        })

    return {
        "commodity_id": cid,
        "segment": seg,
        "n_base": int(n_base),
        "contamination_sensitivity": contam_results,
        "lof_k_sensitivity": k_results,
    }


def run_axis4(data_dir, phase7_dir):
    segments = get_ml_segments(data_dir)
    log_eval("축 4 (민감도) 시작")

    all_results = []

    for cid, seg in segments:
        result = run_sensitivity_segment(phase7_dir, cid, seg)
        all_results.append(result)

        contam_srs = [r["stability_ratio"] for r in result["contamination_sensitivity"]
                      if r["contamination"] != BASE_CONTAMINATION and not np.isnan(r.get("stability_ratio", np.nan))]
        avg_contam_sr = np.mean(contam_srs) if contam_srs else np.nan

        k_srs = [r["stability_ratio"] for r in result["lof_k_sensitivity"]
                 if r["lof_k"] != BASE_LOF_K and not np.isnan(r.get("stability_ratio", np.nan))]
        avg_k_sr = np.mean(k_srs) if k_srs else np.nan

        log_eval(
            f"  {cid:12s} {seg}: "
            f"base={result['n_base']}, "
            f"contam_SR_avg={avg_contam_sr:.3f}, "
            f"k_SR_avg={avg_k_sr:.3f}"
        )

    log_eval("축 4 완료")
    return all_results


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    PHASE7_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7")
    run_axis4(DATA_DIR, PHASE7_DIR)
