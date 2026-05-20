"""
축 4 -- 파라미터 민감도 (로버스트니스)
======================================
역할:
  ML 하이퍼파라미터를 변화시켜 탐지 결과의 안정성을 검증한다.

  변동 1: contamination/nu = 0.05, 0.10, 0.15 (3세트, 3종 모델 연동)
  변동 2: LOF k = 5, 10, 15, 20 (4세트, LOF 단독)

  안정성 비율(Stability Ratio) 산출:
    SR = |S_base 교집합 S_alt| / |S_base|
    SR >= 0.80: 강건, 0.60~0.80: 보통, < 0.60: 취약

입력 파일:
  - data/processed/phase7/stat_timeseries/{cid}_{seg}_stat_timeseries.csv
  - data/processed/phase7/phase7_summary.csv
  - data/processed/product_config.json

출력: 민감도 분석 결과 dict

위치: tests/phase7_ml/test_axis4_sensitivity.py
"""

import sys
import os
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# phase7_ml_common에서 피처 로딩 함수 가져오기
# tests에서 src 모듈 접근
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
    """주어진 파라미터로 3종 모델을 실행하고 ml_detected를 반환한다."""
    # IF
    if_model = IsolationForest(
        n_estimators=100, contamination=contamination, random_state=RANDOM_STATE
    )
    if_model.fit(X_scaled)
    if_labels = if_model.predict(X_scaled)

    # LOF
    lof_model = LocalOutlierFactor(
        n_neighbors=lof_k, contamination=contamination, novelty=False
    )
    lof_labels = lof_model.fit_predict(X_scaled)

    # SVM
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
    """안정성 비율을 산출한다."""
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

    # 기본값 실행
    base_detected = run_models_with_params(
        X_scaled, contamination=BASE_CONTAMINATION, lof_k=BASE_LOF_K
    )
    n_base = base_detected.sum()

    # contamination/nu 변동
    contam_results = []
    for c in CONTAMINATION_VALUES:
        alt_detected = run_models_with_params(X_scaled, contamination=c, lof_k=BASE_LOF_K)
        sr = compute_stability_ratio(base_detected, alt_detected)
        contam_results.append({
            "contamination": c,
            "n_detected": int(alt_detected.sum()),
            "stability_ratio": round(sr, 4) if not np.isnan(sr) else np.nan,
        })

    # LOF k값 변동
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
    """전 20개 구간에 대해 민감도 분석을 수행한다."""
    segments = get_ml_segments(data_dir)
    log_eval("축 4 (민감도) 시작")

    all_results = []

    for cid, seg in segments:
        result = run_sensitivity_segment(phase7_dir, cid, seg)
        all_results.append(result)

        # contamination SR 요약
        contam_srs = [r["stability_ratio"] for r in result["contamination_sensitivity"]
                      if r["contamination"] != BASE_CONTAMINATION and not np.isnan(r.get("stability_ratio", np.nan))]
        avg_contam_sr = np.mean(contam_srs) if contam_srs else np.nan

        # k값 SR 요약
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
