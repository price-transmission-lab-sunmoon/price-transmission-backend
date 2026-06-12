"""
Phase 2 — 정상성 검정 (Stationarity Test)

목적:
    Phase 1 산출물(계절 조정 시계열)의 정상성을 ADF + KPSS 병행 검정으로 판단한다.
    비정상 시계열은 1차 차분(변화율) 후 재검정하여, Phase 3(공적분 검정) 및
    Phase 4(VAR/VECM 추정)의 입력 데이터 형태를 확정한다.

검정 로직:
    ADF 귀무가설: 단위근 존재(비정상) → p < 0.05 시 기각 → 정상
    KPSS 귀무가설: 정상 → p < 0.05 시 기각 → 비정상

    | ADF    | KPSS   | 판정   |
    |--------|--------|--------|
    | 정상   | 정상   | 정상   |
    | 비정상 | 비정상 | 비정상 |
    | 정상   | 비정상 | 비정상 (보수적) |
    | 비정상 | 정상   | 비정상 (보수적) |

입력:
    data/processed/phase1/seasonal_adjusted/{cid}_sa.csv
    data/processed/product_config.json

출력:
    data/processed/phase2/stationarity_results.csv    — 전체 검정 결과 테이블
    data/processed/phase2/integration_orders.json     — 품목·컬럼별 적분 차수 (Phase 3 입력)

실행:
    python src/preprocessing/phase2_stationarity_test.py

작성일: 2026-04-12
"""

import os
import json
import warnings
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller, kpss

# 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SA_DIR = os.path.join(BASE_DIR, "data", "processed", "phase1", "seasonal_adjusted")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "processed", "product_config.json")
PHASE2_DIR = os.path.join(BASE_DIR, "data", "processed", "phase2")

# 검정 파라미터
SIGNIFICANCE_LEVEL = 0.05
ADF_AUTOLAG = "AIC"
KPSS_REGRESSION = "c"       # 상수항만 포함 (추세 미포함)
KPSS_NLAGS = "auto"


def load_config(config_path: str) -> dict:
    """product_config.json 로드"""
    with open(config_path, encoding="utf-8-sig") as f:
        return json.load(f)


def get_analysis_columns(config_entry: dict) -> list:
    """품목 설정에서 분석 대상 컬럼 목록 추출"""
    cols = set()
    for pair in config_entry["segment_pairs"].values():
        cols.update(pair)
    return sorted(cols)


def load_sa_data(commodity_id: str, sa_dir: str) -> pd.DataFrame:
    """Phase 1 계절 조정 데이터 로드"""
    path = os.path.join(sa_dir, f"{commodity_id}_sa.csv")
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


# ADF + KPSS 병행 검정
def run_adf_test(series: pd.Series) -> dict:
    """
    ADF 검정 실행.
    H0: 단위근 존재 (비정상) → p < α 시 기각 → 정상
    """
    result = adfuller(series.dropna(), autolag=ADF_AUTOLAG)
    return {
        "adf_stat": result[0],
        "adf_pvalue": result[1],
        "adf_lags": result[2],
        "adf_nobs": result[3],
        "adf_stationary": result[1] < SIGNIFICANCE_LEVEL,  # True = 정상
    }


def run_kpss_test(series: pd.Series) -> dict:
    """
    KPSS 검정 실행.
    H0: 정상 → p < α 시 기각 → 비정상

    참고: statsmodels KPSS의 p-value는 [0.01, 0.10] 범위로 클리핑됨.
          p=0.01 → 확실히 비정상, p=0.10 → 확실히 정상.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # KPSS interpolation warning 억제
        stat, pvalue, lags, crit = kpss(
            series.dropna(), regression=KPSS_REGRESSION, nlags=KPSS_NLAGS
        )
    return {
        "kpss_stat": stat,
        "kpss_pvalue": pvalue,
        "kpss_lags": lags,
        "kpss_stationary": pvalue >= SIGNIFICANCE_LEVEL,  # True = 정상
    }


def joint_judgment(adf_stationary: bool, kpss_stationary: bool) -> str:
    """
    ADF + KPSS 병행 판정.

    보수적 원칙: 둘 중 하나라도 비정상이면 비정상으로 판정.

    Returns: 'stationary' | 'non-stationary'
    """
    if adf_stationary and kpss_stationary:
        return "stationary"
    else:
        return "non-stationary"


def determine_conflict_note(adf_stationary: bool, kpss_stationary: bool) -> str:
    """ADF-KPSS 판정 일치 여부 기록"""
    if adf_stationary and kpss_stationary:
        return "일치 (둘 다 정상)"
    elif not adf_stationary and not kpss_stationary:
        return "일치 (둘 다 비정상)"
    elif adf_stationary and not kpss_stationary:
        return "상충 → 비정상 (보수적)"
    else:  # not adf_stationary and kpss_stationary
        return "상충 → 비정상 (보수적)"


def test_stationarity(series: pd.Series) -> dict:
    """
    단일 시계열에 대해 ADF + KPSS 병행 검정을 실행하고
    수준(level) 데이터가 비정상이면 1차 차분 후 재검정한다.

    Returns
    -------
    dict : 수준 검정 결과, (필요 시) 차분 검정 결과, 최종 적분 차수
    """
    adf = run_adf_test(series)
    kpss_res = run_kpss_test(series)
    level_judgment = joint_judgment(adf["adf_stationary"], kpss_res["kpss_stationary"])
    conflict_note = determine_conflict_note(adf["adf_stationary"], kpss_res["kpss_stationary"])

    result = {
        # 수준 검정 결과
        "level_adf_stat": round(adf["adf_stat"], 4),
        "level_adf_pvalue": round(adf["adf_pvalue"], 4),
        "level_adf_lags": adf["adf_lags"],
        "level_adf_stationary": adf["adf_stationary"],
        "level_kpss_stat": round(kpss_res["kpss_stat"], 4),
        "level_kpss_pvalue": round(kpss_res["kpss_pvalue"], 4),
        "level_kpss_stationary": kpss_res["kpss_stationary"],
        "level_judgment": level_judgment,
        "level_conflict_note": conflict_note,
    }

    if level_judgment == "stationary":
        # 수준에서 정상 → 적분 차수 I(0)
        result.update({
            "diff_adf_stat": None,
            "diff_adf_pvalue": None,
            "diff_kpss_stat": None,
            "diff_kpss_pvalue": None,
            "diff_judgment": None,
            "integration_order": 0,
        })
    else:
        # 수준에서 비정상 → 1차 차분 후 재검정
        diff_series = series.diff().dropna()
        adf_d = run_adf_test(diff_series)
        kpss_d = run_kpss_test(diff_series)
        diff_judgment = joint_judgment(adf_d["adf_stationary"], kpss_d["kpss_stationary"])

        result.update({
            "diff_adf_stat": round(adf_d["adf_stat"], 4),
            "diff_adf_pvalue": round(adf_d["adf_pvalue"], 4),
            "diff_kpss_stat": round(kpss_d["kpss_stat"], 4),
            "diff_kpss_pvalue": round(kpss_d["kpss_pvalue"], 4),
            "diff_judgment": diff_judgment,
            "integration_order": 1 if diff_judgment == "stationary" else 2,
        })

    return result


# 통합 실행
def run_phase2(sa_dir: str = SA_DIR,
               config_path: str = CONFIG_PATH,
               output_dir: str = PHASE2_DIR):
    """Phase 2 전체 파이프라인 실행"""

    os.makedirs(output_dir, exist_ok=True)

    config = load_config(config_path)
    all_results = []
    integration_orders = {}

    print("=" * 60)
    print("Phase 2 — 정상성 검정 (ADF + KPSS)")
    print("=" * 60)

    for commodity_id, cfg in config.items():
        print(f"\n{'─' * 40}")
        print(f"[{commodity_id}] {cfg['name_kr']} ({cfg['name_en']})")

        df = load_sa_data(commodity_id, sa_dir)
        analysis_cols = get_analysis_columns(cfg)
        integration_orders[commodity_id] = {}

        for col in analysis_cols:
            sa_col = f"{col}_sa"
            if sa_col not in df.columns:
                continue

            series = df[sa_col]
            result = test_stationarity(series)

            # 결과 기록
            row = {
                "commodity_id": commodity_id,
                "column": col,
                "n_obs": len(series.dropna()),
                **result,
            }
            all_results.append(row)
            integration_orders[commodity_id][col] = result["integration_order"]

            # 콘솔 출력
            level_icon = "✓" if result["level_judgment"] == "stationary" else "✗"
            level_str = f"수준: ADF p={result['level_adf_pvalue']:.4f}, KPSS p={result['level_kpss_pvalue']:.4f} → {result['level_judgment']}"

            if result["integration_order"] == 0:
                print(f"  {col:25s} | {level_icon} {level_str} | I(0)")
            else:
                diff_icon = "✓" if result["diff_judgment"] == "stationary" else "✗"
                diff_str = f"차분: ADF p={result['diff_adf_pvalue']:.4f}, KPSS p={result['diff_kpss_pvalue']:.4f} → {result['diff_judgment']}"
                print(f"  {col:25s} | {level_icon} {level_str}")
                print(f"  {'':25s} | {diff_icon} {diff_str} | I({result['integration_order']})")

    results_df = pd.DataFrame(all_results)
    results_path = os.path.join(output_dir, "stationarity_results.csv")
    results_df.to_csv(results_path, index=False, encoding="utf-8-sig")

    orders_path = os.path.join(output_dir, "integration_orders.json")
    with open(orders_path, "w", encoding="utf-8") as f:
        json.dump(integration_orders, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print("Phase 2 완료!")
    print(f"  검정 결과:     {results_path}")
    print(f"  적분 차수:     {orders_path}")
    print(f"{'─' * 60}")

    # 요약 통계 — 빈 결과 방어
    total = len(results_df)
    if total == 0:
        print("  결과 없음 (입력 데이터 부재)")
        print(f"{'=' * 60}")
        return results_df, integration_orders

    i0_level = len(results_df[results_df["integration_order"] == 0])
    i1 = len(results_df[results_df["integration_order"] == 1])
    i2 = len(results_df[results_df["integration_order"] == 2])
    conflicts = len(results_df[results_df["level_conflict_note"].str.contains("상충")])

    print(f"  총 시계열: {total}개")
    print(f"  I(0) 수준 정상: {i0_level}개")
    print(f"  I(1) 1차 차분 후 정상: {i1}개")
    if i2 > 0:
        print(f"  I(2) 2차 차분 필요: {i2}개 ⚠️")
    print(f"  ADF-KPSS 상충: {conflicts}개")

    # Phase 3 가이드
    print(f"\n{'─' * 60}")
    print("Phase 3 가이드:")
    print("  I(1) 시계열 쌍 → Johansen 공적분 검정 대상")
    print("  I(0) 시계열 → 수준 VAR 직접 적용 가능")
    if i2 > 0:
        print("  I(2) 시계열 → 2차 차분 또는 분석 제외 검토 필요")
    print(f"{'=' * 60}")

    return results_df, integration_orders


# 엔트리포인트
if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    run_phase2()
