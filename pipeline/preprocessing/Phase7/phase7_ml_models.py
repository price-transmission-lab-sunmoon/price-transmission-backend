"""
Phase 7-ML 모델 실행 + 앙상블 집계 (phase7_ml_models.py)
========================================================
역할:
  Isolation Forest, LOF, One-Class SVM 3종 모델을 실행하고,
  앙상블 집계(ml_consensus_count, ml_detected)를 산출한다.

입력:
  X_scaled (ndarray): 전처리된 피처 행렬 (n x 6)

출력:
  predictions DataFrame: 3종 모델 판정 + 앙상블 결과

모델 파라미터 (settings.py 기준):
  IF:  n_estimators=100, contamination=0.08, random_state=42
  LOF: n_neighbors=10, contamination=0.08, novelty=False
  SVM: kernel='rbf', nu=0.08, gamma='scale'
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM


# ---------------------------------------------------------------------------
# 파라미터 (settings.py 기준값)
# ---------------------------------------------------------------------------
RANDOM_STATE = 42
IF_N_ESTIMATORS = 100
CONTAMINATION = 0.08
LOF_N_NEIGHBORS = 10
SVM_KERNEL = "rbf"
SVM_NU = 0.08
SVM_GAMMA = "scale"

# 앙상블 기준: 2개 이상 모델이 이상 판정 시 ml_detected=True
ML_CONSENSUS_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Isolation Forest
# ---------------------------------------------------------------------------
def run_isolation_forest(X_scaled):
    """
    Isolation Forest를 실행한다.

    Returns:
        (if_anomaly ndarray[bool], if_score ndarray[float], model IsolationForest)
    """
    model = IsolationForest(
        n_estimators=IF_N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
    )
    model.fit(X_scaled)
    labels = model.predict(X_scaled)
    scores = model.score_samples(X_scaled)

    if_anomaly = labels == -1
    return if_anomaly, scores, model


# ---------------------------------------------------------------------------
# LOF (Local Outlier Factor)
# ---------------------------------------------------------------------------
def run_lof(X_scaled):
    """
    Local Outlier Factor를 실행한다.

    novelty=False: 전체 기간 transductive 방식.
    저장된 모델은 재현/감사 용도. 새 데이터에 predict() 호출 불가.

    Returns:
        (lof_anomaly ndarray[bool], lof_score ndarray[float], model LocalOutlierFactor)
    """
    model = LocalOutlierFactor(
        n_neighbors=LOF_N_NEIGHBORS,
        contamination=CONTAMINATION,
        novelty=False,
    )
    labels = model.fit_predict(X_scaled)
    scores = model.negative_outlier_factor_

    lof_anomaly = labels == -1
    return lof_anomaly, scores, model


# ---------------------------------------------------------------------------
# One-Class SVM
# ---------------------------------------------------------------------------
def run_ocsvm(X_scaled):
    """
    One-Class SVM을 실행한다.

    전체 기간 단일 fit.

    Returns:
        (svm_anomaly ndarray[bool], svm_score ndarray[float], model OneClassSVM)
    """
    model = OneClassSVM(
        kernel=SVM_KERNEL,
        nu=SVM_NU,
        gamma=SVM_GAMMA,
    )
    model.fit(X_scaled)
    labels = model.predict(X_scaled)
    scores = model.decision_function(X_scaled)

    svm_anomaly = labels == -1
    return svm_anomaly, scores, model


# ---------------------------------------------------------------------------
# 3종 모델 실행 + 앙상블 집계
# ---------------------------------------------------------------------------
def run_all_models(X_scaled, valid_index):
    """
    3종 모델을 실행하고 앙상블 집계를 산출한다.

    Args:
        X_scaled: 전처리된 피처 행렬 (n x 6)
        valid_index: 결측 제거 후 남은 날짜 인덱스

    Returns:
        (predictions DataFrame, models dict)
    """
    # 3종 모델 실행
    if_anomaly, if_score, if_model = run_isolation_forest(X_scaled)
    lof_anomaly, lof_score, lof_model = run_lof(X_scaled)
    svm_anomaly, svm_score, svm_model = run_ocsvm(X_scaled)

    # 앙상블 집계
    ml_consensus_count = (
        if_anomaly.astype(int) + lof_anomaly.astype(int) + svm_anomaly.astype(int)
    )
    ml_detected = ml_consensus_count >= ML_CONSENSUS_THRESHOLD

    # 결과 DataFrame
    predictions = pd.DataFrame(
        {
            "date": valid_index,
            "if_anomaly": if_anomaly,
            "if_score": if_score,
            "lof_anomaly": lof_anomaly,
            "lof_score": lof_score,
            "svm_anomaly": svm_anomaly,
            "svm_score": svm_score,
            "ml_consensus_count": ml_consensus_count,
            "ml_detected": ml_detected,
        }
    )

    models = {
        "isolation_forest": if_model,
        "lof": lof_model,
        "ocsvm": svm_model,
    }

    return predictions, models