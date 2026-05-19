"""
Phase 7-ML 실행 진입점 (phase7_ml_run.py)
==========================================
역할:
  품목 x 구간(A, B) 20개 조합에 대해 Phase 7-ML 전체 파이프라인을 실행한다.
  피처 구성 -> 전처리 -> 3종 모델 -> 앙상블 -> 교차 대조 -> 신뢰도 등급화.

입력 파일:
  - data/processed/phase7/stat_timeseries/{cid}_{seg}_stat_timeseries.csv (20개)
  - data/processed/phase7/phase7_summary.csv
  - data/processed/product_config.json

출력 파일:
  - data/processed/phase7_ml/features/{cid}_{seg}_features.csv           (20개)
  - data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv  (20개)
  - data/processed/phase7_ml/cross_validation/{cid}_{seg}_cross_val.csv  (20개)
  - data/processed/phase7_ml/confidence_grades/{cid}_{seg}_grades.csv    (20개)

실행 방법:
  python src/preprocessing/Phase7/phase7_ml_run.py
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


# ---------------------------------------------------------------------------
# 단일 구간 실행
# ---------------------------------------------------------------------------
def run_ml_segment(phase7_dir, output_base, cid, seg, run_date):
    """
    단일 품목x구간에 대해 Phase 7-ML 전체 파이프라인을 실행한다.

    Returns:
        dict (통계 요약)
    """
    # (1) 피처 행렬 구성
    features_raw, dates = load_feature_matrix(phase7_dir, cid, seg)

    # (2) 전처리 (결측 제거 + 스케일링)
    X_scaled, valid_index, scaler = preprocess_features(features_raw)

    n_total = len(features_raw)
    n_valid = len(valid_index)
    n_dropped = n_total - n_valid

    # (3) 3종 모델 실행 + 앙상블
    predictions, models = run_all_models(X_scaled, valid_index)

    # (4) stat_detected 조인
    stat_df = load_stat_detected(phase7_dir, cid, seg, valid_index)

    # (5) 교차 대조
    cross_val = build_cross_validation(predictions, stat_df)

    # (6) 신뢰도 등급화 (confidence_grade=None 제외)
    grades = assign_confidence_grades(cross_val)

    # --- 파일 저장 ---

    # 학습된 모델 + 스케일러 저장 (재현/감사 용도)
    # 파일명에 실행 날짜를 포함하여 버전 관리
    models_dir = output_base / "models" / run_date
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(models["isolation_forest"], models_dir / f"{cid}_{seg}_if_{run_date}.pkl")
    joblib.dump(models["lof"], models_dir / f"{cid}_{seg}_lof_{run_date}.pkl")
    joblib.dump(models["ocsvm"], models_dir / f"{cid}_{seg}_svm_{run_date}.pkl")
    joblib.dump(scaler, models_dir / f"{cid}_{seg}_scaler_{run_date}.pkl")

    # features CSV (스케일링 전 원본, 결측 포함)
    features_out = features_raw.copy()
    features_out.insert(0, "date", dates.values)
    features_out.insert(1, "commodity_id", cid)
    features_out.insert(2, "segment", seg)
    features_path = output_base / "features" / f"{cid}_{seg}_features.csv"
    features_out.to_csv(features_path, index=False, encoding="utf-8-sig")

    # predictions CSV
    predictions.insert(1, "commodity_id", cid)
    predictions.insert(2, "segment", seg)
    pred_path = output_base / "predictions" / f"{cid}_{seg}_ml_predictions.csv"
    predictions.to_csv(pred_path, index=False, encoding="utf-8-sig")

    # cross_validation CSV
    cross_val.insert(1, "commodity_id", cid)
    cross_val.insert(2, "segment", seg)
    cv_path = output_base / "cross_validation" / f"{cid}_{seg}_cross_val.csv"
    cross_val.to_csv(cv_path, index=False, encoding="utf-8-sig")

    # confidence_grades CSV (confidence_grade != None만)
    grades.insert(1, "commodity_id", cid)
    grades.insert(2, "segment", seg)
    grades_path = output_base / "confidence_grades" / f"{cid}_{seg}_grades.csv"
    grades.to_csv(grades_path, index=False, encoding="utf-8-sig")

    # 통계 집계
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


# ---------------------------------------------------------------------------
# 전체 실행
# ---------------------------------------------------------------------------
def run_phase7_ml(data_dir, phase7_dir, output_dir):
    """
    전 20개 구간(A, B)에 대해 Phase 7-ML을 실행한다.

    Args:
        data_dir: 데이터 루트 디렉토리 (product_config.json 위치)
        phase7_dir: Phase 7 stat 출력 디렉토리
        output_dir: Phase 7-ML 출력 디렉토리
    """
    # product_config 로드
    config_path = os.path.join(data_dir, "product_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    output_base = ensure_ml_output_dirs(output_dir)
    
    run_date = datetime.now().strftime("%Y%m%d_%H%M")

    # 구간 목록 구성
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

# 전체 요약 통계
    stats_df = pd.DataFrame(all_stats)
    summary_path = output_base / "phase7_ml_summary.csv"
    stats_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # 전체 합계
    total_ml = stats_df["ml_detected"].sum()
    total_high = stats_df["grade_high"].sum()
    total_medium = stats_df["grade_medium"].sum()
    total_ref = stats_df["grade_reference"].sum()

    # --- 실행 로그 저장 (재현/감사 용도) ---
    # 주석 처리 또는 삭제: run_date = datetime.now().strftime("%Y%m%d")
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    run_log = {
        "run_date": run_date,  # 상단에서 정의한 %Y%m%d_%H%M 가 그대로 유지됩니다.
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

    # 로그 폴더 경로와 파일명 모두 시·분 폴더 내부를 정확히 바라보게 됩니다.
    log_dir = output_base / "models" / run_date
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_log_{run_date}.json"
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2, ensure_ascii=False)

    log_ml(f"Phase 7-ML 완료")
    log_ml(f"  ML 탐지: {total_ml}건")
    log_ml(f"  신뢰도: high={total_high}, medium={total_medium}, reference={total_ref}")
    log_ml(f"  요약: {summary_path}")
    log_ml(f"  실행 로그: {log_path}")

    return stats_df


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------
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
