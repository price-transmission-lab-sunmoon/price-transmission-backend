"""
Phase 7-ML 교차 대조 + 신뢰도 등급화.

high: 통계+ML 동시 탐지 / medium: 통계만 / reference: ML만 / None: 정상(DB 미적재)
"""

import pandas as pd
import numpy as np


def build_cross_validation(predictions, stat_df):
    """통계 탐지와 ML 탐지를 date 기준으로 교차 대조한다."""
    cross = predictions[["date", "ml_detected", "ml_consensus_count"]].merge(
        stat_df[["date", "stat_detected", "pattern_type"]],
        on="date",
        how="left",
    )

    cross["stat_detected"] = cross["stat_detected"].fillna(False).astype(bool)
    cross["agreement"] = cross["stat_detected"] == cross["ml_detected"]

    return cross


def assign_confidence_grades(cross_val):
    """신뢰도 등급 부여 후 confidence_grade != None 행만 반환."""
    grades = cross_val.copy()

    conditions = [
        grades["stat_detected"] & grades["ml_detected"],
        grades["stat_detected"] & ~grades["ml_detected"],
        ~grades["stat_detected"] & grades["ml_detected"],
    ]
    choices = ["high", "medium", "reference"]

    grades["confidence_grade"] = np.select(conditions, choices, default=None)

    # 정상 월(None) 제외
    grades = grades[grades["confidence_grade"].notna()].copy()
    grades = grades.reset_index(drop=True)

    return grades
