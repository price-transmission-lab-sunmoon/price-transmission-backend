"""
Phase 7-ML 교차 대조 + 신뢰도 등급화 (phase7_ml_cross.py)
==========================================================
역할:
  통계 탐지(stat_detected)와 ML 탐지(ml_detected)를 교차 대조하고,
  신뢰도 등급(high/medium/reference)을 부여한다.
  confidence_grade=None인 정상 월은 최종 출력에서 제외한다.

입력:
  predictions DataFrame (phase7_ml_models.py 산출)
  stat_detected DataFrame (phase7_ml_common.py 산출)

출력:
  cross_val DataFrame: 교차 대조 결과 (전 시점)
  grades DataFrame: 신뢰도 등급 (confidence_grade != None 행만)

신뢰도 등급:
  high      : 통계 + ML 동시 탐지 (고신뢰)
  medium    : 통계 탐지, ML 미탐지 (중신뢰)
  reference : ML 탐지, 통계 미탐지 (참고)
  None      : 둘 다 미탐지 (정상, DB 미적재)
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 교차 대조
# ---------------------------------------------------------------------------
def build_cross_validation(predictions, stat_df):
    """
    통계 탐지와 ML 탐지를 교차 대조한다.

    Args:
        predictions: ML 예측 결과 DataFrame (date, ml_detected 등)
        stat_df: 통계 탐지 DataFrame (date, stat_detected, pattern_type)

    Returns:
        cross_val DataFrame (전 시점)
    """
    # date 기준 merge
    cross = predictions[["date", "ml_detected", "ml_consensus_count"]].merge(
        stat_df[["date", "stat_detected", "pattern_type"]],
        on="date",
        how="left",
    )

    # stat_detected 결측 채우기 (predictions에만 있는 날짜)
    cross["stat_detected"] = cross["stat_detected"].fillna(False).astype(bool)

    # agreement 산출
    cross["agreement"] = cross["stat_detected"] == cross["ml_detected"]

    return cross


# ---------------------------------------------------------------------------
# 신뢰도 등급화
# ---------------------------------------------------------------------------
def assign_confidence_grades(cross_val):
    """
    교차 대조 결과에 신뢰도 등급을 부여한다.

    confidence_grade=None인 정상 월은 제외하여 반환한다.

    Args:
        cross_val: 교차 대조 DataFrame

    Returns:
        grades DataFrame (confidence_grade != None 행만)
    """
    grades = cross_val.copy()

    conditions = [
        grades["stat_detected"] & grades["ml_detected"],
        grades["stat_detected"] & ~grades["ml_detected"],
        ~grades["stat_detected"] & grades["ml_detected"],
    ]
    choices = ["high", "medium", "reference"]

    grades["confidence_grade"] = np.select(conditions, choices, default=None)

    # None인 행(정상 월) 제외 — DB 적재 규칙 D-02
    grades = grades[grades["confidence_grade"].notna()].copy()
    grades = grades.reset_index(drop=True)

    return grades
