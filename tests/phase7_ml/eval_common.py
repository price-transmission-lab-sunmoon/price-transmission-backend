"""
ML 평가 공통 모듈 (eval_common.py)
===================================
역할:
  외부 충격 사건 정의, 품목x충격 매핑, ML 탐지 가능 기간 판별,
  데이터 로딩 함수를 제공한다. 축 1(ESR)과 축 5(CTA+ASC+P_stat+P_ml)에서 공유.

변경 이력:
  v2 (2026-05-14):
    - E3(브라질 서리), E5(인도네시아 팜유 수출 규제) 삭제
      사유: E3-E4, E4-E5 윈도우 겹침 → 충격 간 분리 불가
    - E6(러시아 가뭄·수출 금지 2010.08~2011.06) 추가
    - E9(역대급 엘니뇨 2015.09~2016.06) 추가
    - is_date_in_shock_windows() 헬퍼 함수 추가 (P_stat, P_ml 산출용)

위치: tests/phase7_ml/eval_common.py
"""

import pandas as pd
import numpy as np
import json
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# 외부 충격 사건 정의 (시간순 정렬)
# ---------------------------------------------------------------------------
EXTERNAL_SHOCKS = [
    {
        "id": "E1",
        "name": "2008 글로벌 금융위기",
        "start": "2008-07-01",
        "end": "2009-01-01",
        "commodities": ["wheat", "maize", "soybean", "palmoil", "sugar",
                        "coffee", "beef", "groundnuts", "banana", "orange"],
    },
    {
        "id": "E6",
        "name": "2010 러시아 가뭄·수출 금지",
        "start": "2010-08-01",
        "end": "2011-06-01",
        "commodities": ["wheat", "maize", "soybean", "palmoil", "sugar",
                        "coffee", "beef"],
    },
    {
        "id": "E9",
        "name": "2015-16 역대급 엘니뇨",
        "start": "2015-09-01",
        "end": "2016-06-01",
        "commodities": ["maize", "soybean", "palmoil", "sugar",
                        "coffee", "beef"],
    },
    {
        "id": "E2",
        "name": "2020 COVID-19 팬데믹",
        "start": "2020-02-01",
        "end": "2020-06-01",
        "commodities": ["wheat", "maize", "soybean", "palmoil", "sugar",
                        "coffee", "beef", "groundnuts", "banana", "orange"],
    },
    {
        "id": "E4",
        "name": "2022 우크라이나 전쟁",
        "start": "2022-02-01",
        "end": "2022-10-01",
        "commodities": ["wheat", "maize", "soybean", "palmoil"],
    },
]


# ---------------------------------------------------------------------------
# ML 탐지 가능 기간 산출
# ---------------------------------------------------------------------------
def get_ml_detectable_range(data_dir, cid, seg):
    """
    품목x구간의 ML 탐지 가능 기간을 반환한다.

    ML 탐지 가능 = warmup_end 이후 ~ common_end.
    dropna로 인해 실제 predictions에 빈 행이 있을 수 있으나,
    기간 범위 판별에는 warmup_end와 common_end를 사용한다.

    Returns:
        (detect_start Timestamp, detect_end Timestamp)
    """
    data_dir = Path(data_dir)
    baseline = json.load(
        open(data_dir / "phase4" / "baseline" / f"{cid}_{seg}_baseline.json", encoding="utf-8")
    )
    config = json.load(open(data_dir / "product_config.json", encoding="utf-8"))

    warmup_end = pd.Timestamp(baseline["warmup_end"] + "-01")
    common_end = pd.Timestamp(config[cid]["common_end"] + "-01")

    # 탐지 가능 시작 = warmup_end 다음 달
    detect_start = warmup_end + pd.DateOffset(months=1)
    detect_end = common_end

    return detect_start, detect_end


def is_shock_in_detectable_range(shock, detect_start, detect_end):
    """
    충격 윈도우가 ML 탐지 가능 기간과 겹치는지 확인한다.

    1개월이라도 겹치면 True.
    """
    shock_start = pd.Timestamp(shock["start"])
    shock_end = pd.Timestamp(shock["end"])
    return shock_start <= detect_end and shock_end >= detect_start


def get_applicable_shocks(data_dir, cid, seg):
    """
    품목x구간에 대해 적용 가능한 외부 충격 목록을 반환한다.

    조건:
      1. 해당 품목이 충격의 commodities에 포함
      2. 충격 윈도우가 ML 탐지 가능 기간과 겹침

    Returns:
        list of shock dicts
    """
    detect_start, detect_end = get_ml_detectable_range(data_dir, cid, seg)

    applicable = []
    for shock in EXTERNAL_SHOCKS:
        if cid not in shock["commodities"]:
            continue
        if not is_shock_in_detectable_range(shock, detect_start, detect_end):
            continue
        applicable.append(shock)

    return applicable


# ---------------------------------------------------------------------------
# 충격 윈도우 판별 헬퍼 (P_stat, P_ml 산출용)
# ---------------------------------------------------------------------------
def is_date_in_shock_windows(date, shocks):
    """
    특정 날짜가 주어진 충격 목록의 윈도우 중 하나에 포함되는지 확인한다.

    Args:
        date: 확인할 날짜 (Timestamp)
        shocks: 적용 가능한 충격 목록 (get_applicable_shocks 반환값)

    Returns:
        True if date is within any shock window, False otherwise
    """
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        if s_start <= date <= s_end:
            return True
    return False


# ---------------------------------------------------------------------------
# 데이터 로딩
# ---------------------------------------------------------------------------
def load_predictions(ml_dir, cid, seg):
    """predictions CSV를 로드한다."""
    path = Path(ml_dir) / "predictions" / f"{cid}_{seg}_ml_predictions.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_cross_val(ml_dir, cid, seg):
    """cross_validation CSV를 로드한다."""
    path = Path(ml_dir) / "cross_validation" / f"{cid}_{seg}_cross_val.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_grades(ml_dir, cid, seg):
    """confidence_grades CSV를 로드한다."""
    path = Path(ml_dir) / "confidence_grades" / f"{cid}_{seg}_grades.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_all_predictions(ml_dir):
    """전 구간 predictions를 합쳐서 반환한다."""
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "predictions")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "predictions" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def load_all_cross_val(ml_dir):
    """전 구간 cross_val을 합쳐서 반환한다."""
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "cross_validation")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "cross_validation" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def load_all_grades(ml_dir):
    """전 구간 grades를 합쳐서 반환한다."""
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "confidence_grades")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "confidence_grades" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def get_ml_segments(data_dir):
    """ML 적용 구간(A, B) 목록을 반환한다."""
    config = json.load(open(Path(data_dir) / "product_config.json", encoding="utf-8"))
    segments = []
    for cid, cfg in config.items():
        for seg in cfg["segments"]:
            if seg in ["A", "B"]:
                segments.append((cid, seg))
    return segments


# ---------------------------------------------------------------------------
# 로깅
# ---------------------------------------------------------------------------
def log_eval(msg):
    """평가 로그 출력."""
    print(f"[ML-Eval] {msg}")