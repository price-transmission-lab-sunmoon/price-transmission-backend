"""
Phase 7-ML 공통 모듈 (phase7_ml_common.py)
==========================================
역할:
  Phase 7-ML에서 사용하는 피처 행렬 구성, 전처리(결측 제거, 스케일링),
  stat_detected 조인 로직을 제공한다.

입력 파일:
  - data/processed/phase7/stat_timeseries/{cid}_{seg}_stat_timeseries.csv
  - data/processed/phase7/phase7_summary.csv

출력 파일:
  없음 (라이브러리 모듈)

피처 목록 (6종 고정):
  F1 transmission_rate   : 월별 전이율
  F2 upstream_pct        : 상류 가격 변화율 (%)
  F3 downstream_pct      : 하류 가격 변화율 (%)
  F4 ect_or_spread       : ECT 또는 로그 스프레드 (Phase 4 산출물 직접 사용)
  F5 exchange_rate_pct   : 환율 월 변동률 (%)
  F6 intl_price_usd_pct  : 달러 국제가 월 변동률 (%)

순환 논리 방지:
  Phase 7 통계 판정 결과(zscore, pattern_flag 등)는 피처에서 완전 제외한다.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, RobustScaler
from pathlib import Path


# ---------------------------------------------------------------------------
# 피처 컬럼 정의
# ---------------------------------------------------------------------------
FEATURE_COLUMNS = [
    "transmission_rate",
    "upstream_pct",
    "downstream_pct",
    "ect_or_spread",
    "exchange_rate_pct",
    "intl_price_usd_pct",
]

# ML 적용 구간
ML_SEGMENTS = ["A", "B"]


# ---------------------------------------------------------------------------
# 피처 행렬 구성
# ---------------------------------------------------------------------------
def load_feature_matrix(phase7_dir, cid, seg):
    """
    stat_timeseries CSV에서 6종 피처를 추출한다.

    stat_timeseries의 날짜 컬럼은 'period'이며,
    반환 DataFrame의 인덱스는 'date'로 통일한다.

    Args:
        phase7_dir: Phase 7 출력 루트 디렉토리
        cid: 품목 ID
        seg: 구간 ID

    Returns:
        (features_raw DataFrame, dates Series)
        features_raw: 6종 피처 (결측 포함, 스케일링 전)
        dates: 날짜 Series
    """
    phase7 = Path(phase7_dir)
    st_path = phase7 / "stat_timeseries" / f"{cid}_{seg}_stat_timeseries.csv"
    st = pd.read_csv(st_path, encoding="utf-8-sig")

    # 날짜 컬럼 통일 (stat_timeseries는 'period', summary는 'date')
    st["date"] = pd.to_datetime(st["period"])
    dates = st["date"]

    features_raw = st[FEATURE_COLUMNS].copy()
    features_raw.index = dates

    return features_raw, dates


# ---------------------------------------------------------------------------
# 전처리 (결측 제거 + 스케일링)
# ---------------------------------------------------------------------------
def preprocess_features(features_raw):
    """
    피처 행렬에서 결측을 제거하고 StandardScaler를 적용한다.

    결측이 있는 행(월) 전체를 제외한다.
    전체 기간 단일 fit (품목x구간 조합별 독립).

    Args:
        features_raw: 6종 피처 DataFrame (결측 포함)

    Returns:
        (X_scaled ndarray, valid_index DatetimeIndex, scaler StandardScaler)
        X_scaled: 스케일링된 피처 행렬 (n_valid x 6)
        valid_index: 결측 제거 후 남은 날짜 인덱스
        scaler: fit된 StandardScaler 객체
    """
    # 결측 제거
    features_valid = features_raw.dropna()
    valid_index = features_valid.index

    # StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(features_valid.values)

    return X_scaled, valid_index, scaler

# ---------------------------------------------------------------------------
# stat_detected 조인
# ---------------------------------------------------------------------------
def load_stat_detected(phase7_dir, cid, seg, all_dates):
    """
    phase7_summary.csv에서 해당 품목x구간의 stat_detected를 조회한다.

    phase7_summary는 탐지 이벤트만 기록(stat_detected=True 고정)하므로,
    summary에 없는 날짜는 stat_detected=False로 채운다.

    Args:
        phase7_dir: Phase 7 출력 루트 디렉토리
        cid: 품목 ID
        seg: 구간 ID
        all_dates: 전체 날짜 Series 또는 DatetimeIndex

    Returns:
        stat_df DataFrame (date, stat_detected, pattern_type)
    """
    phase7 = Path(phase7_dir)
    summary_path = phase7 / "phase7_summary.csv"
    sm = pd.read_csv(summary_path, encoding="utf-8-sig")
    sm["date"] = pd.to_datetime(sm["date"])

    # 해당 품목x구간 필터
    mask = (sm["commodity_id"] == cid) & (sm["segment"] == seg)
    sm_seg = sm[mask][["date", "stat_detected", "pattern_type"]].copy()

    # 전체 날짜 기준으로 LEFT JOIN
    all_dates_df = pd.DataFrame({"date": pd.to_datetime(all_dates)})
    result = all_dates_df.merge(sm_seg, on="date", how="left")

    # summary에 없는 날짜는 stat_detected=False
    result["stat_detected"] = result["stat_detected"].fillna(False).astype(bool)

    return result


# ---------------------------------------------------------------------------
# 출력 디렉토리 생성
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 로깅
# ---------------------------------------------------------------------------
def log_ml(msg):
    """간단한 콘솔 로그 출력."""
    print(f"[Phase7-ML] {msg}")