"""
Phase 7-ML 실행 진입점 — A/B 구간 20개 조합에 대해 ML 파이프라인 실행.

입력: phase7/stat_timeseries, phase7_summary.csv, product_config.json
출력: phase7_ml/features, predictions, cross_validation, confidence_grades (각 20개)
"""

import sys
import os
import json
import pandas as pd
import joblib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase7_ml_common import (
    FEATURE_COLUMNS,
    ML_SEGMENTS,
    load_feature_matrix,
    preprocess_features,
    load_stat_detected,
    ensure_ml_output_dirs,
    log_ml,
)
from phase7_ml_models import run_all_models
from phase7_ml_cross import build_cross_validation, assign_confidence_grades


def run_ml_segment(phase7_dir, output_base, cid, seg, run_date):
    """단일 품목x구간에 대해 Phase 7-ML 전체 파이프라인을 실행한다. 반환: 통계 dict."""
    features_raw, dates = load_feature_matrix(phase7_dir, cid, seg)
    X_scaled, valid_index, scaler = preprocess_features(features_raw)

    n_total = len(features_raw)
    n_valid = len(valid_index)
    n_dropped = n_total - n_valid

    predictions, models = run_all_models(X_scaled, valid_index)
    stat_df = load_stat_detected(phase7_dir, cid, seg, valid_index)
    cross_val = build_cross_validation(predictions, stat_df)
    grades = assign_confidence_grades(cross_val)

    # 모델 + 스케일러 저장 (파일명에 실행 날짜 포함하여 버전 관리)
    models_dir = output_base / "models" / run_date
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(models["isolation_forest"], models_dir / f"{cid}_{seg}_if_{run_date}.pkl")
    joblib.dump(models["lof"], models_dir / f"{cid}_{seg}_lof_{run_date}.pkl")
    joblib.dump(models["ocsvm"], models_dir / f"{cid}_{seg}_svm_{run_date}.pkl")
    joblib.dump(scaler, models_dir / f"{cid}_{seg}_scaler_{run_date}.pkl")

    features_out = features_raw.copy()
    features_out.insert(0, "date", dates.values)
    features_out.insert(1, "commodity_id", cid)
    features_out.insert(2, "segment", seg)
    features_path = output_base / "features" / f"{cid}_{seg}_features.csv"
    features_out.to_csv(features_path, index=False, encoding="utf-8-sig")

    predictions.insert(1, "commodity_id", cid)
    predictions.insert(2, "segment", seg)
    pred_path = output_base / "predictions" / f"{cid}_{seg}_ml_predictions.csv"
    predictions.to_csv(pred_path, index=False, encoding="utf-8-sig")

    cross_val.insert(1, "commodity_id", cid)
    cross_val.insert(2, "segment", seg)
    cv_path = output_base / "cross_validation" / f"{cid}_{seg}_cross_val.csv"
    cross_val.to_csv(cv_path, index=False, encoding="utf-8-sig")

    grades.insert(1, "commodity_id", cid)
    grades.insert(2, "segment", seg)
    grades_path = output_base / "confidence_grades" / f"{cid}_{seg}_grades.csv"
    grades.to_csv(grades_path, index=False, encoding="utf-8-sig")

    n_ml_detected = predictions["ml_detected"].sum()
    n_if = predictions["if_anomaly"].sum()
    n_lof = predictions["lof_anomaly"].sum()
    n_svm = predictions["svm_anomaly"].sum()

    n_high = int((grades["confidence_grade"] == "high").sum()) if len(grades) > 0 else 0
    n_medium = int((grades["confidence_grade"] == "medium").sum()) if len(grades) > 0 else 0
    n_reference = int((grades["confidence_grade"] == "reference").sum()) if len(grades) > 0 else 0

    stats = {
        "commodity_id": cid,
        "segment": seg,
        "total_months": n_total,
        "valid_months": n_valid,
        "dropped_months": n_dropped,
        "if_anomaly": int(n_if),
        "lof_anomaly": int(n_lof),
        "svm_anomaly": int(n_svm),
        "ml_detected": int(n_ml_detected),
        "grade_high": n_high,
        "grade_medium": n_medium,
        "grade_reference": n_reference,
    }

    return stats


def run_phase7_ml(data_dir, phase7_dir, output_dir):
    """A/B 구간 20개 조합에 대해 Phase 7-ML을 실행한다."""
    config_path = os.path.join(data_dir, "product_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    output_base = ensure_ml_output_dirs(output_dir)
    run_date = datetime.now().strftime("%Y%m%d_%H%M")

    segments = []
    for cid, cfg in config.items():
        for seg in cfg["segments"]:
            if seg in ML_SEGMENTS:
                segments.append((cid, seg))

    log_ml(f"Phase 7-ML 시작: {len(segments)}개 구간")
    all_stats = []

    for cid, seg in segments:
        stats = run_ml_segment(phase7_dir, output_base, cid, seg, run_date)
        all_stats.append(stats)

        log_ml(
            f"  {cid:12s} {seg}: "
            f"valid={stats['valid_months']:3d}, "
            f"IF={stats['if_anomaly']:3d}, "
            f"LOF={stats['lof_anomaly']:3d}, "
            f"SVM={stats['svm_anomaly']:3d}, "
            f"ml_detected={stats['ml_detected']:3d} | "
            f"high={stats['grade_high']:2d}, "
            f"medium={stats['grade_medium']:2d}, "
            f"ref={stats['grade_reference']:2d}"
        )

    stats_df = pd.DataFrame(all_stats)
    summary_path = output_base / "phase7_ml_summary.csv"
    stats_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    total_ml = stats_df["ml_detected"].sum()
    total_high = stats_df["grade_high"].sum()
    total_medium = stats_df["grade_medium"].sum()
    total_ref = stats_df["grade_reference"].sum()

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    run_log = {
        "run_date": run_date,
        "run_timestamp": run_timestamp,
        "parameters": {
            "isolation_forest": {
                "n_estimators": 100,
                "contamination": 0.08,
                "random_state": 42,
            },
            "lof": {
                "n_neighbors": 10,
                "contamination": 0.08,
                "novelty": False,
            },
            "ocsvm": {
                "kernel": "rbf",
                "nu": 0.08,
                "gamma": "scale",
            },
            "preprocessing": {
                "scaler": "StandardScaler",
                "feature_columns": FEATURE_COLUMNS,
                "ml_segments": ML_SEGMENTS,
                "consensus_threshold": 2,
                "transmission_rate_min_upstream": 0.5,
            },
        },
        "results": {
            "total_segments": len(segments),
            "total_valid_months": int(stats_df["valid_months"].sum()),
            "total_ml_detected": int(total_ml),
            "grade_high": int(total_high),
            "grade_medium": int(total_medium),
            "grade_reference": int(total_ref),
        },
        "segment_results": all_stats,
        "pkl_files": [
            f"{cid}_{seg}_{model}_{run_date}.pkl"
            for cid, seg in segments
            for model in ["if", "lof", "svm", "scaler"]
        ],
    }

    log_dir = output_base / "models" / run_date
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_log_{run_date}.json"

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2, ensure_ascii=False)

    log_ml("Phase 7-ML 완료")
    log_ml(f"  ML 탐지: {total_ml}건")
    log_ml(f"  신뢰도: high={total_high}, medium={total_medium}, reference={total_ref}")
    log_ml(f"  요약: {summary_path}")
    log_ml(f"  실행 로그: {log_path}")

    return stats_df


if __name__ == "__main__":
    DATA_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed"
    )
    PHASE7_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7"
    )
    OUTPUT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7_ml"
    )

    stats_df = run_phase7_ml(DATA_DIR, PHASE7_DIR, OUTPUT_DIR)

    print()
    print("=== Phase 7-ML 전체 요약 ===")
    print(stats_df.to_string(index=False))
