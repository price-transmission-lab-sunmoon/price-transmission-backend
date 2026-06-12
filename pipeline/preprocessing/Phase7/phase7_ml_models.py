"""
Phase 7-ML — Isolation Forest, LOF, One-Class SVM 실행 + 앙상블 집계.

파라미터: IF(n_estimators=100, contamination=0.08), LOF(n_neighbors=10), SVM(rbf, nu=0.08)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM


RANDOM_STATE = 42
IF_N_ESTIMATORS = 100
CONTAMINATION = 0.08
LOF_N_NEIGHBORS = 10
SVM_KERNEL = "rbf"
SVM_NU = 0.08
SVM_GAMMA = "scale"

# 2개 이상 모델이 이상 판정 시 ml_detected=True
ML_CONSENSUS_THRESHOLD = 2


def run_isolation_forest(X_scaled):
    """Isolation Forest 실행. 반환: (if_anomaly, if_score, model)."""
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


def run_lof(X_scaled):
    """
    LOF 실행. novelty=False: transductive 방식이므로 새 데이터 predict 불가.
    반환: (lof_anomaly, lof_score, model).
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


def run_ocsvm(X_scaled):
    """One-Class SVM 실행. 반환: (svm_anomaly, svm_score, model)."""
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


def run_all_models(X_scaled, valid_index):
    """3종 모델 실행 후 앙상블 집계. 반환: (predictions DataFrame, models dict)."""
    if_anomaly, if_score, if_model = run_isolation_forest(X_scaled)
    lof_anomaly, lof_score, lof_model = run_lof(X_scaled)
    svm_anomaly, svm_score, svm_model = run_ocsvm(X_scaled)

    # 2개 이상 이상 판정 시 ml_detected=True
    ml_consensus_count = (
        if_anomaly.astype(int) + lof_anomaly.astype(int) + svm_anomaly.astype(int)
    )
    ml_detected = ml_consensus_count >= ML_CONSENSUS_THRESHOLD

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