"""
Phase 1 — 계절 조정 (Seasonal Adjustment)

목적:
    Phase 0 산출물(merged CSV)에 STL 분해를 적용하여 계절 성분을 제거하고,
    계절 조정 시계열에서 전월 대비 변화율을 산출한다.
    로버스트니스 체크용으로 계절 더미 방식도 병행 산출한다.

입력:
    data/processed/merged/{commodity_id}.csv          — Phase 0 통합 데이터셋
    data/processed/product_config.json                — 품목별 분석 설정

출력:
    data/processed/phase1/seasonal_adjusted/{cid}_sa.csv        — 계절 조정 시계열 (수준)
    data/processed/phase1/changes/{cid}_changes.csv             — 전월 대비 변화율 (%)
    data/processed/phase1/stl_components/{cid}_stl.csv          — STL 분해 성분 (trend, seasonal, resid)
    data/processed/phase1/robustness/{cid}_dummy_sa.csv         — 계절 더미 방식 계절 조정
    data/processed/phase1/robustness/{cid}_dummy_changes.csv    — 계절 더미 방식 변화율
    data/processed/phase1/phase1_summary.csv                    — 처리 요약 리포트

실행:
    python src/preprocessing/phase1_seasonal_adjustment.py

작성일: 2026-04-11
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL
from sklearn.linear_model import LinearRegression

# ──────────────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MERGED_DIR = os.path.join(BASE_DIR, "data", "processed", "merged")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "processed", "product_config.json")

PHASE1_DIR = os.path.join(BASE_DIR, "data", "processed", "phase1")
SA_DIR = os.path.join(PHASE1_DIR, "seasonal_adjusted")
CHANGES_DIR = os.path.join(PHASE1_DIR, "changes")
STL_DIR = os.path.join(PHASE1_DIR, "stl_components")
ROBUST_DIR = os.path.join(PHASE1_DIR, "robustness")

# ──────────────────────────────────────────────
# STL 파라미터
# ──────────────────────────────────────────────
STL_PERIOD = 12          # 월별 데이터 → 12개월 주기
STL_ROBUST = True        # 이상치에 강건한 추정
# seasonal, trend 윈도우는 statsmodels 기본값 사용 (seasonal=7, trend=auto)

# 분석 대상 가격 컬럼 (segment_pairs에서 사용되는 컬럼만)
# exchange_rate는 외생변수로 Phase 7-ML에서 변화율만 별도 산출하므로 여기선 제외
PRICE_COLS_BASE = ["intl_price_krw", "import_price_usd", "ppi", "cpi"]
PRICE_COL_WHOLESALE = "wholesale_price"

# exchange_rate는 STL 대상은 아니지만, Phase 7-ML 피처로 변화율이 필요
EXOG_COLS = ["exchange_rate", "intl_price_usd"]


def load_config(config_path: str) -> dict:
    """product_config.json 로드"""
    with open(config_path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_commodity_data(commodity_id: str, merged_dir: str) -> pd.DataFrame:
    """품목별 merged CSV 로드 및 날짜 인덱스 설정"""
    path = os.path.join(merged_dir, f"{commodity_id}.csv")
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.index.freq = "MS"  # Month Start
    return df


def get_analysis_columns(config_entry: dict) -> list:
    """품목 설정에서 STL 적용 대상 컬럼 목록 추출"""
    cols = set()
    for pair in config_entry["segment_pairs"].values():
        cols.update(pair)
    return sorted(cols)


# ──────────────────────────────────────────────
# Step 1: STL 분해 및 계절 조정
# ──────────────────────────────────────────────
def apply_stl(series: pd.Series, period: int = STL_PERIOD,
              robust: bool = STL_ROBUST) -> dict:
    """
    단일 시계열에 STL 분해를 적용한다.

    Parameters
    ----------
    series : pd.Series
        월별 시계열 (DatetimeIndex, freq='MS')
    period : int
        계절 주기 (12 = 월별)
    robust : bool
        이상치 강건 추정 여부

    Returns
    -------
    dict with keys: 'sa' (계절 조정), 'trend', 'seasonal', 'resid'
    """
    stl = STL(series, period=period, robust=robust)
    result = stl.fit()

    sa = series - result.seasonal  # 계절 조정 = 원 시계열 - 계절 성분

    return {
        "sa": sa,
        "trend": result.trend,
        "seasonal": result.seasonal,
        "resid": result.resid,
    }


def process_stl_commodity(df: pd.DataFrame, analysis_cols: list) -> tuple:
    """
    품목 데이터프레임의 모든 분석 대상 컬럼에 STL 적용.

    Returns
    -------
    (sa_df, stl_df) :
        sa_df  — 계절 조정 시계열 (컬럼: {col}_sa)
        stl_df — STL 3성분 (컬럼: {col}_trend, {col}_seasonal, {col}_resid)
    """
    sa_records = {}
    stl_records = {}

    for col in analysis_cols:
        if col not in df.columns:
            continue

        result = apply_stl(df[col])
        sa_records[f"{col}_sa"] = result["sa"]
        stl_records[f"{col}_trend"] = result["trend"]
        stl_records[f"{col}_seasonal"] = result["seasonal"]
        stl_records[f"{col}_resid"] = result["resid"]

    sa_df = pd.DataFrame(sa_records, index=df.index)
    stl_df = pd.DataFrame(stl_records, index=df.index)

    return sa_df, stl_df


# ──────────────────────────────────────────────
# Step 2: 전월 대비 변화율 산출
# ──────────────────────────────────────────────
def compute_pct_change(sa_df: pd.DataFrame) -> pd.DataFrame:
    """
    계절 조정 시계열에서 전월 대비 변화율(%)을 산출한다.

    공식: (X_t - X_{t-1}) / X_{t-1} × 100
    첫 행은 NaN.

    입력 컬럼명이 '{col}_sa'이면 출력 컬럼명은 '{col}_pct'로 변환.
    """
    pct_df = sa_df.pct_change() * 100

    # 컬럼명 변환: _sa → _pct
    rename_map = {c: c.replace("_sa", "_pct") for c in pct_df.columns}
    pct_df = pct_df.rename(columns=rename_map)

    return pct_df


def compute_exog_pct_change(df: pd.DataFrame, exog_cols: list) -> pd.DataFrame:
    """
    외생 변수(환율, 달러 국제가)의 전월 대비 변화율을 산출한다.
    STL 적용 없이 원 시계열에서 직접 변화율 산출.

    Phase 7-ML 피처로 사용:
    - exchange_rate → exchange_rate_pct
    - intl_price_usd → intl_price_usd_pct
    """
    records = {}
    for col in exog_cols:
        if col in df.columns:
            records[f"{col}_pct"] = df[col].pct_change() * 100
    return pd.DataFrame(records, index=df.index)


# ──────────────────────────────────────────────
# Step 3: 계절 더미 방식 (로버스트니스 체크용)
# ──────────────────────────────────────────────
def apply_seasonal_dummy(series: pd.Series) -> pd.Series:
    """
    월별 더미 변수 OLS 회귀로 계절 성분을 추정·제거한다.

    방법:
        y_t = α + Σ(β_m × D_m) + ε_t   (m = 2, ..., 12; 1월 기준)
        계절 성분 = Σ(β_m × D_m)
        계절 조정 시계열 = y_t - 계절 성분 = α + ε_t

    STL 대비 단순하며, Phase 8 로버스트니스 체크에서 비교 대상으로 사용.
    """
    months = series.index.month
    # 11개 더미 변수 (1월 = 기준)
    X_dummy = pd.get_dummies(months, drop_first=True, dtype=float).values

    reg = LinearRegression().fit(X_dummy, series.values)

    # 계절 성분 = 더미 효과만 (절편 제외)
    seasonal_component = X_dummy @ reg.coef_

    # 계절 조정 = 원 시계열 - 계절 성분
    sa = pd.Series(series.values - seasonal_component, index=series.index, name=series.name)

    return sa


def process_dummy_commodity(df: pd.DataFrame, analysis_cols: list) -> tuple:
    """
    품목 데이터의 모든 분석 대상 컬럼에 계절 더미 방식 적용.

    Returns
    -------
    (dummy_sa_df, dummy_pct_df)
    """
    sa_records = {}

    for col in analysis_cols:
        if col not in df.columns:
            continue
        sa_records[f"{col}_sa"] = apply_seasonal_dummy(df[col])

    dummy_sa_df = pd.DataFrame(sa_records, index=df.index)
    dummy_pct_df = dummy_sa_df.pct_change() * 100
    dummy_pct_df = dummy_pct_df.rename(
        columns={c: c.replace("_sa", "_pct") for c in dummy_pct_df.columns}
    )

    return dummy_sa_df, dummy_pct_df


# ──────────────────────────────────────────────
# 통합 실행
# ──────────────────────────────────────────────
def run_phase1(merged_dir: str = MERGED_DIR,
               config_path: str = CONFIG_PATH,
               output_base: str = PHASE1_DIR):
    """Phase 1 전체 파이프라인 실행"""

    # 출력 디렉토리 생성
    sa_dir = os.path.join(output_base, "seasonal_adjusted")
    changes_dir = os.path.join(output_base, "changes")
    stl_dir = os.path.join(output_base, "stl_components")
    robust_dir = os.path.join(output_base, "robustness")

    for d in [sa_dir, changes_dir, stl_dir, robust_dir]:
        os.makedirs(d, exist_ok=True)

    # 설정 로드
    config = load_config(config_path)
    summary_rows = []

    print("=" * 60)
    print("Phase 1 — 계절 조정 (Seasonal Adjustment)")
    print("=" * 60)

    for commodity_id, cfg in config.items():
        print(f"\n{'─' * 40}")
        print(f"[{commodity_id}] {cfg['name_kr']} ({cfg['name_en']})")
        print(f"  기간: {cfg['common_start']} ~ {cfg['common_end']} ({cfg['common_months']}개월)")
        print(f"  도매가: {'있음' if cfg['has_wholesale'] else '없음'}")

        # 1. 데이터 로드
        df = load_commodity_data(commodity_id, merged_dir)
        analysis_cols = get_analysis_columns(cfg)
        print(f"  분석 컬럼: {analysis_cols}")

        # 2. STL 분해 및 계절 조정 (Step 1)
        sa_df, stl_df = process_stl_commodity(df, analysis_cols)

        # 원본 컬럼도 함께 저장 (비교 용이)
        sa_output = df[["commodity_id"]].copy()
        for col in analysis_cols:
            if col in df.columns:
                sa_output[col] = df[col]                    # 원본
                sa_output[f"{col}_sa"] = sa_df[f"{col}_sa"]  # 계절 조정

        sa_output.to_csv(os.path.join(sa_dir, f"{commodity_id}_sa.csv"),
                         encoding="utf-8-sig")
        stl_df.to_csv(os.path.join(stl_dir, f"{commodity_id}_stl.csv"),
                       encoding="utf-8-sig")

        # 3. 변화율 산출 (Step 2)
        pct_df = compute_pct_change(sa_df)
        exog_pct = compute_exog_pct_change(df, EXOG_COLS)

        changes_output = df[["commodity_id"]].copy()
        changes_output = pd.concat([changes_output, pct_df, exog_pct], axis=1)
        changes_output.to_csv(os.path.join(changes_dir, f"{commodity_id}_changes.csv"),
                              encoding="utf-8-sig")

        # 4. 계절 더미 방식 (Step 3 — 로버스트니스)
        dummy_sa_df, dummy_pct_df = process_dummy_commodity(df, analysis_cols)

        dummy_sa_df.to_csv(os.path.join(robust_dir, f"{commodity_id}_dummy_sa.csv"),
                           encoding="utf-8-sig")

        dummy_changes_output = df[["commodity_id"]].copy()
        dummy_changes_output = pd.concat([dummy_changes_output, dummy_pct_df, exog_pct], axis=1)
        dummy_changes_output.to_csv(
            os.path.join(robust_dir, f"{commodity_id}_dummy_changes.csv"),
            encoding="utf-8-sig"
        )

        # 5. 요약 통계
        for col in analysis_cols:
            if col not in df.columns:
                continue
            sa_col = f"{col}_sa"
            pct_col = f"{col}_pct"

            seasonal_range = stl_df[f"{col}_seasonal"].max() - stl_df[f"{col}_seasonal"].min()
            seasonal_pct_of_mean = (seasonal_range / df[col].mean() * 100) if df[col].mean() != 0 else 0

            pct_series = pct_df[pct_col].dropna()

            summary_rows.append({
                "commodity_id": commodity_id,
                "column": col,
                "n_obs": len(df),
                "original_mean": round(df[col].mean(), 4),
                "original_std": round(df[col].std(), 4),
                "sa_mean": round(sa_df[sa_col].mean(), 4),
                "sa_std": round(sa_df[sa_col].std(), 4),
                "seasonal_range": round(seasonal_range, 4),
                "seasonal_pct_of_mean": round(seasonal_pct_of_mean, 2),
                "pct_change_mean": round(pct_series.mean(), 4) if len(pct_series) > 0 else None,
                "pct_change_std": round(pct_series.std(), 4) if len(pct_series) > 0 else None,
                "pct_change_min": round(pct_series.min(), 4) if len(pct_series) > 0 else None,
                "pct_change_max": round(pct_series.max(), 4) if len(pct_series) > 0 else None,
            })

        print(f"  ✓ STL 계절 조정 완료")
        print(f"  ✓ 변화율 산출 완료")
        print(f"  ✓ 계절 더미 방식 산출 완료")

    # 요약 리포트 저장
    summary_df = pd.DataFrame(summary_rows)
    summary_path = os.path.join(output_base, "phase1_summary.csv")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 60}")
    print(f"Phase 1 완료!")
    print(f"  계절 조정 시계열: {sa_dir}/")
    print(f"  변화율 데이터:    {changes_dir}/")
    print(f"  STL 성분:        {stl_dir}/")
    print(f"  로버스트니스:     {robust_dir}/")
    print(f"  요약 리포트:      {summary_path}")
    print(f"{'=' * 60}")

    return summary_df


# ──────────────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    run_phase1()
