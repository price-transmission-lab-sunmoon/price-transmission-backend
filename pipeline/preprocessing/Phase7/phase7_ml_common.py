"""
Phase 7-ML 공통 모듈 — 피처 행렬 구성, 전처리, stat_detected 조인.

피처 6종: transmission_rate, upstream_pct, downstream_pct,
          ect_or_spread, exchange_rate_pct, intl_price_usd_pct
순환 논리 방지: zscore 등 통계 판정 결과는 피처에서 제외.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, RobustScaler
from pathlib import Path


FEATURE_COLUMNS = [
    "transmission_rate",
    "upstream_pct",
    "downstream_pct",
    "ect_or_spread",
    "exchange_rate_pct",
    "intl_price_usd_pct",
]

ML_SEGMENTS = ["A", "B"]


def load_feature_matrix(phase7_dir, cid, seg):
    """stat_timeseries CSV에서 6종 피처를 추출한다. 반환: (features_raw, dates)."""
    phase7 = Path(phase7_dir)
    st_path = phase7 / "stat_timeseries" / f"{cid}_{seg}_stat_timeseries.csv"
    st = pd.read_csv(st_path, encoding="utf-8-sig")

    # 날짜 컬럼명 통일 (stat_timeseries는 'period')
    st["date"] = pd.to_datetime(st["period"])
    dates = st["date"]

    features_raw = st[FEATURE_COLUMNS].copy()
    features_raw.index = dates

    return features_raw, dates


def preprocess_features(features_raw):
    """결측 행 제거 후 StandardScaler 적용. 반환: (X_scaled, valid_index, scaler)."""
    features_valid = features_raw.dropna()
    valid_index = features_valid.index

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(features_valid.values)

    return X_scaled, valid_index, scaler


def load_stat_detected(phase7_dir, cid, seg, all_dates):
    """
    phase7_summary.csv에서 stat_detected를 조회한다.
    summary에 없는 날짜는 False로 채운다.
    """
    phase7 = Path(phase7_dir)
    summary_path = phase7 / "phase7_summary.csv"
    sm = pd.read_csv(summary_path, encoding="utf-8-sig")
    sm["date"] = pd.to_datetime(sm["date"])

    mask = (sm["commodity_id"] == cid) & (sm["segment"] == seg)
    sm_seg = sm[mask][["date", "stat_detected", "pattern_type"]].copy()

    all_dates_df = pd.DataFrame({"date": pd.to_datetime(all_dates)})
    result = all_dates_df.merge(sm_seg, on="date", how="left")

    result["stat_detected"] = result["stat_detected"].fillna(False).astype(bool)

    return result


def ensure_ml_output_dirs(output_base):
    """Phase 7-ML 출력 디렉토리 구조를 생성한다."""
    dirs = [
        "features",
        "predictions",
        "cross_validation",
        "confidence_grades",
        "models",
    ]
    output_base = Path(output_base)
    for d in dirs:
        (output_base / d).mkdir(parents=True, exist_ok=True)
    return output_base


def log_ml(msg):
    print(f"[Phase7-ML] {msg}")