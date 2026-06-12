"""ML 평가 공통 모듈 — 외부 충격 사건 정의, 탐지 가능 기간 판별, 데이터 로딩."""

import pandas as pd
import numpy as np
import json
import os
from pathlib import Path


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


def get_ml_detectable_range(data_dir, cid, seg):
    """warmup_end 이후 ~ common_end 범위를 반환한다."""
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
    """충격 윈도우와 ML 탐지 가능 기간이 1개월 이상 겹치면 True."""
    shock_start = pd.Timestamp(shock["start"])
    shock_end = pd.Timestamp(shock["end"])
    return shock_start <= detect_end and shock_end >= detect_start


def get_applicable_shocks(data_dir, cid, seg):
    """품목이 충격 commodities에 포함되고 탐지 가능 기간과 겹치는 충격 목록 반환."""
    detect_start, detect_end = get_ml_detectable_range(data_dir, cid, seg)

    applicable = []
    for shock in EXTERNAL_SHOCKS:
        if cid not in shock["commodities"]:
            continue
        if not is_shock_in_detectable_range(shock, detect_start, detect_end):
            continue
        applicable.append(shock)

    return applicable


def is_date_in_shock_windows(date, shocks):
    """date가 shocks 중 어느 윈도우에든 포함되면 True."""
    for shock in shocks:
        s_start = pd.Timestamp(shock["start"])
        s_end = pd.Timestamp(shock["end"])
        if s_start <= date <= s_end:
            return True
    return False


def load_predictions(ml_dir, cid, seg):
    path = Path(ml_dir) / "predictions" / f"{cid}_{seg}_ml_predictions.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_cross_val(ml_dir, cid, seg):
    path = Path(ml_dir) / "cross_validation" / f"{cid}_{seg}_cross_val.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_grades(ml_dir, cid, seg):
    path = Path(ml_dir) / "confidence_grades" / f"{cid}_{seg}_grades.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_all_predictions(ml_dir):
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "predictions")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "predictions" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def load_all_cross_val(ml_dir):
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "cross_validation")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "cross_validation" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def load_all_grades(ml_dir):
    ml_dir = Path(ml_dir)
    dfs = []
    for f in sorted(os.listdir(ml_dir / "confidence_grades")):
        if f.endswith(".csv"):
            df = pd.read_csv(ml_dir / "confidence_grades" / f)
            df["date"] = pd.to_datetime(df["date"])
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def get_ml_segments(data_dir):
    config = json.load(open(Path(data_dir) / "product_config.json", encoding="utf-8"))
    segments = []
    for cid, cfg in config.items():
        for seg in cfg["segments"]:
            if seg in ["A", "B"]:
                segments.append((cid, seg))
    return segments


def log_eval(msg):
    print(f"[ML-Eval] {msg}")