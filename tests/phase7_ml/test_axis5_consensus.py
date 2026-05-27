"""
축 5 -- 합의 기반 지표 (CTA + ASC + P_stat + P_ml)
====================================================
역할:
  통계-ML 트랙의 탐지 합의를 정량화한다.
  CTA = |통계 교집합 ML| / |통계 합집합 ML|
  ASC = |합의 시점 중 충격 윈도우 내| / |합의 시점 총|

  정밀도 지표 (신규):
  P_stat = |통계 탐지 ∩ 충격 윈도우 내| / |통계 탐지 총 시점|
  P_ml   = |ML 탐지 ∩ 충격 윈도우 내| / |ML 탐지 총 시점|

  핵심 가설: ASC > max(P_stat, P_ml)
    → 합의 기반 탐지의 정밀도가 단일 트랙 탐지의 정밀도보다 높다
    → 세 지표 모두 precision 형태로 차원 통일

  보조 지표 (recall 형태, 변경 없음):
  ESR_stat, ESR_ml — 민감도 기술용으로 함께 보고

변경 이력:
  v2 (2026-05-14):
    - P_stat, P_ml 산출 추가
    - 핵심 가설 ASC > max(ESR_stat, ESR_ml) → ASC > max(P_stat, P_ml) 변경
    - ESR_stat, ESR_ml은 보조 지표로 유지

입력 파일:
  - data/processed/phase7_ml/cross_validation/{cid}_{seg}_cross_val.csv
  - data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/product_config.json

출력: CTA, ASC, P_stat, P_ml, ESR_stat, ESR_ml 결과 dict

위치: tests/phase7_ml/test_axis5_consensus.py
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import (
    EXTERNAL_SHOCKS,
    get_applicable_shocks,
    is_date_in_shock_windows,
    load_cross_val,
    load_predictions,
    get_ml_segments,
    log_eval,
)


def compute_cta(cv_df):
    """
    Cross-Track Agreement를 산출한다.
    CTA = |stat 교집합 ml| / |stat 합집합 ml|
    """
    stat = cv_df["stat_detected"].values
    ml = cv_df["ml_detected"].values

    intersection = (stat & ml).sum()
    union = (stat | ml).sum()

    if union == 0:
        return np.nan
    return intersection / union


def compute_asc(cv_df, shocks):
    """
    Agreement-to-Shock Coincidence를 산출한다.
    ASC = |합의 시점 중 충격 윈도우 내| / |합의 시점 총|
    """
    # 합의 시점 = stat + ml 동시 탐지
    consensus = cv_df[cv_df["stat_detected"] & cv_df["ml_detected"]]
    n_consensus = len(consensus)

    if n_consensus == 0:
        return np.nan, 0

    # 충격 윈도우 내 합의 건수
    in_shock = 0
    for _, row in consensus.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    asc = in_shock / n_consensus
    return asc, n_consensus


def compute_p_stat(cv_df, shocks):
    """
    통계 트랙의 충격 정밀도를 산출한다.
    P_stat = |통계 탐지 ∩ 충격 윈도우 내| / |통계 탐지 총 시점|

    "통계가 이상이라고 탐지한 시점 중, 실제 충격 기간과 겹치는 비율"

    Returns:
        (p_stat float, n_stat_detected int)
    """
    stat_detected = cv_df[cv_df["stat_detected"] == True]
    n_stat = len(stat_detected)

    if n_stat == 0:
        return np.nan, 0

    in_shock = 0
    for _, row in stat_detected.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    return in_shock / n_stat, n_stat


def compute_p_ml(cv_df, pred_df, shocks):
    """
    ML 트랙의 충격 정밀도를 산출한다.
    P_ml = |ML 탐지 ∩ 충격 윈도우 내| / |ML 탐지 총 시점|

    "ML이 이상이라고 탐지한 시점 중, 실제 충격 기간과 겹치는 비율"

    Note:
        ml_detected는 predictions CSV 기준으로 산출.
        cross_val에도 ml_detected가 있지만, predictions가 원본.

    Returns:
        (p_ml float, n_ml_detected int)
    """
    ml_detected = pred_df[pred_df["ml_detected"] == True]
    n_ml = len(ml_detected)

    if n_ml == 0:
        return np.nan, 0

    in_shock = 0
    for _, row in ml_detected.iterrows():
        if is_date_in_shock_windows(row["date"], shocks):
            in_shock += 1

    return in_shock / n_ml, n_ml


def compute_esr_stat(cv_df, shocks):
    """
    통계 트랙의 ESR을 산출한다 (보조 지표).
    ESR_stat = (충격 윈도우 내 통계 탐지 1건+ → 회수) / 총 충격 수
    """
    n_shocks = len(shocks)
    if n_shocks == 0:
        return np.nan

    recalled = 0
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        window = cv_df[
            (cv_df["date"] >= s_start) & (cv_df["date"] <= s_end)
        ]
        if window["stat_detected"].any():
            recalled += 1

    return recalled / n_shocks


def compute_esr_ml(pred_df, shocks):
    """
    ML 트랙의 ESR을 산출한다 (보조 지표).
    ESR_ml = (충격 윈도우 내 ML 탐지 1건+ → 회수) / 총 충격 수
    """
    n_shocks = len(shocks)
    if n_shocks == 0:
        return np.nan

    recalled = 0
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        window = pred_df[
            (pred_df["date"] >= s_start) & (pred_df["date"] <= s_end)
        ]
        if window["ml_detected"].any():
            recalled += 1

    return recalled / n_shocks


def run_axis5(data_dir, ml_dir):
    """전 20개 구간에 대해 CTA, ASC, P_stat, P_ml을 산출한다."""
    segments = get_ml_segments(data_dir)
    log_eval("축 5 (CTA + ASC + P_stat + P_ml) 시작")

    all_results = []

    for cid, seg in segments:
        cv = load_cross_val(ml_dir, cid, seg)
        pred = load_predictions(ml_dir, cid, seg)
        shocks = get_applicable_shocks(data_dir, cid, seg)
        n_shocks = len(shocks)

        # --- 기존 지표 ---
        cta = compute_cta(cv)
        asc, n_consensus = compute_asc(cv, shocks)

        # --- 신규 정밀도 지표 ---
        p_stat, n_stat_detected = compute_p_stat(cv, shocks)
        p_ml, n_ml_detected = compute_p_ml(cv, pred, shocks)

        # --- 보조 지표 (recall) ---
        esr_stat = compute_esr_stat(cv, shocks)
        esr_ml = compute_esr_ml(pred, shocks)

        # --- 핵심 가설 검증: ASC > max(P_stat, P_ml) ---
        if (not np.isnan(asc) and not np.isnan(p_stat) and not np.isnan(p_ml)):
            hypothesis_holds = asc > max(p_stat, p_ml)
        else:
            hypothesis_holds = None

        result = {
            "commodity_id": cid,
            "segment": seg,
            "cta": round(cta, 4) if not np.isnan(cta) else np.nan,
            "asc": round(asc, 4) if not np.isnan(asc) else np.nan,
            "n_consensus": n_consensus,
            "p_stat": round(p_stat, 4) if not np.isnan(p_stat) else np.nan,
            "p_ml": round(p_ml, 4) if not np.isnan(p_ml) else np.nan,
            "n_stat_detected": n_stat_detected,
            "n_ml_detected": n_ml_detected,
            "esr_stat": round(esr_stat, 4) if not np.isnan(esr_stat) else np.nan,
            "esr_ml": round(esr_ml, 4) if not np.isnan(esr_ml) else np.nan,
            "n_shocks": n_shocks,
            "hypothesis_holds": hypothesis_holds,
        }
        all_results.append(result)

        hyp_str = "O" if hypothesis_holds else ("X" if hypothesis_holds is False else "-")
        log_eval(
            f"  {cid:12s} {seg}: "
            f"CTA={result['cta']}, ASC={result['asc']}, "
            f"P_stat={result['p_stat']}, P_ml={result['p_ml']}, "
            f"ESR_stat={result['esr_stat']}, ESR_ml={result['esr_ml']}, "
            f"ASC>max(P)={hyp_str}"
        )

    log_eval("축 5 완료")
    return all_results


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    run_axis5(DATA_DIR, ML_DIR)