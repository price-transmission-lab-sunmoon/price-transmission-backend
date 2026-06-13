"""
Phase 3. Johansen 공적분 검정으로 구간별 VAR/VECM 분기 결정.

Trace + Max-Eigenvalue 병행; 충돌 시 Trace 우선(표본 크기에 강건).
시차: AIC 기준 VAR 최적 시차 - 1 (범위 1~4).

입력:
    data/processed/phase1/seasonal_adjusted/{cid}_sa.csv
    data/processed/product_config.json
    data/processed/phase2/integration_orders.json

출력:
    data/processed/phase3/cointegration_results.csv
    data/processed/phase3/model_routing.json
"""

import os
import json
import warnings
import pandas as pd
import numpy as np
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from statsmodels.tsa.api import VAR

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SA_DIR = os.path.join(BASE_DIR, "data", "processed", "phase1", "seasonal_adjusted")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "processed", "product_config.json")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "processed", "phase2", "integration_orders.json")
PHASE3_DIR = os.path.join(BASE_DIR, "data", "processed", "phase3")

MAX_LAG = 4              # VAR 시차 탐색 범위 상한
DET_ORDER = 0            # 상수항 포함, 추세 미포함
SIGNIFICANCE_LEVEL = 0.05
CRIT_INDEX = 1           # 임계값 인덱스: 1 = 5% 유의수준


def load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_integration_orders(orders_path: str) -> dict:
    with open(orders_path, encoding="utf-8") as f:
        return json.load(f)


def load_sa_data(commodity_id: str, sa_dir: str) -> pd.DataFrame:
    path = os.path.join(sa_dir, f"{commodity_id}_sa.csv")
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


def select_var_lag(pair_data: pd.DataFrame, max_lag: int = MAX_LAG) -> dict:
    """VAR AIC/BIC 기준 최적 시차 선택. 실패 시 기본값 1 반환."""
    try:
        var_model = VAR(pair_data)
        result = var_model.select_order(maxlags=max_lag)
        # TODO: 래그 선정 기준을 AIC 단독에서 HQC 등 추가 기준과 비교 검토
        return {
            "aic": max(result.aic, 1),
            "bic": max(result.bic, 1),
        }
    except Exception:
        return {"aic": 1, "bic": 1}


def run_johansen_test(pair_data: pd.DataFrame, k_ar_diff: int) -> dict:
    """
    Johansen 공적분 검정. r=0 귀무가설(공적분 없음)에 대한 Trace/Max-Eigen 통계량 반환.
    Trace만 기각 시 Trace 우선 적용.
    """
    result = coint_johansen(pair_data, det_order=DET_ORDER, k_ar_diff=k_ar_diff)

    trace_stat_r0 = result.lr1[0]
    trace_crit_r0 = result.cvt[0, CRIT_INDEX]
    trace_reject_r0 = trace_stat_r0 > trace_crit_r0

    eigen_stat_r0 = result.lr2[0]
    eigen_crit_r0 = result.cvm[0, CRIT_INDEX]
    eigen_reject_r0 = eigen_stat_r0 > eigen_crit_r0

    if trace_reject_r0 and eigen_reject_r0:
        cointegrated = True
        judgment_note = "Trace, Max-Eigen 모두 기각. 공적분 확정"
    elif trace_reject_r0 and not eigen_reject_r0:
        cointegrated = True
        judgment_note = "Trace만 기각. Trace 우선 적용 (공적분)"
    elif not trace_reject_r0 and eigen_reject_r0:
        cointegrated = False
        judgment_note = "Max-Eigen만 기각. 보수적으로 공적분 없음"
    else:
        cointegrated = False
        judgment_note = "둘 다 미기각. 공적분 없음"

    return {
        "trace_stat_r0": round(trace_stat_r0, 4),
        "trace_crit_r0": round(trace_crit_r0, 4),
        "trace_reject_r0": trace_reject_r0,
        "eigen_stat_r0": round(eigen_stat_r0, 4),
        "eigen_crit_r0": round(eigen_crit_r0, 4),
        "eigen_reject_r0": eigen_reject_r0,
        "cointegrated": cointegrated,
        "judgment_note": judgment_note,
    }


def check_integration_compatibility(orders: dict, commodity_id: str,
                                     upstream: str, downstream: str) -> dict:
    """둘 다 I(1)이면 Johansen 적합; 불일치 시 주의 플래그 부착."""
    order_up = orders.get(commodity_id, {}).get(upstream, None)
    order_down = orders.get(commodity_id, {}).get(downstream, None)

    if order_up == 1 and order_down == 1:
        return {"compatible": True, "flag": None}
    elif order_up is None or order_down is None:
        return {"compatible": False, "flag": "적분 차수 정보 없음"}
    else:
        return {
            "compatible": True,  # 진행은 하되 플래그 부착
            "flag": f"적분 차수 불일치: {upstream}=I({order_up}), {downstream}=I({order_down})"
        }


def run_phase3(sa_dir: str = SA_DIR,
               config_path: str = CONFIG_PATH,
               orders_path: str = ORDERS_PATH,
               output_dir: str = PHASE3_DIR):
    """Phase 3 전체 파이프라인 실행."""

    os.makedirs(output_dir, exist_ok=True)

    config = load_config(config_path)
    orders = load_integration_orders(orders_path)

    all_results = []
    model_selection = {}

    print("=" * 60)
    print("Phase 3. Johansen 공적분 검정")
    print("=" * 60)

    for commodity_id, cfg in config.items():
        print(f"\n{'─' * 40}")
        print(f"[{commodity_id}] {cfg['name_kr']} ({cfg['name_en']})")

        df = load_sa_data(commodity_id, sa_dir)
        model_selection[commodity_id] = {}

        for segment, pair_cols in cfg["segment_pairs"].items():
            upstream, downstream = pair_cols
            upstream_sa = f"{upstream}_sa"
            downstream_sa = f"{downstream}_sa"

            if upstream_sa not in df.columns or downstream_sa not in df.columns:
                print(f"  구간 {segment}: 컬럼 누락 ({upstream_sa} or {downstream_sa})")
                continue

            compat = check_integration_compatibility(orders, commodity_id, upstream, downstream)

            pair_data = df[[upstream_sa, downstream_sa]].dropna()
            n_obs = len(pair_data)

            lag_info = select_var_lag(pair_data)
            johansen_lag = max(lag_info["aic"] - 1, 1)

            try:
                johansen = run_johansen_test(pair_data, k_ar_diff=johansen_lag)
            except Exception as e:
                print(f"  구간 {segment}: 검정 실패 ({e})")
                johansen = {
                    "trace_stat_r0": None, "trace_crit_r0": None, "trace_reject_r0": None,
                    "eigen_stat_r0": None, "eigen_crit_r0": None, "eigen_reject_r0": None,
                    "cointegrated": None, "judgment_note": f"검정 실패: {e}",
                }

            if johansen["cointegrated"]:
                model = "VECM"
            elif johansen["cointegrated"] is None:
                model = "UNKNOWN"
            else:
                model = "VAR"

            model_selection[commodity_id][segment] = {
                "model": model,
                "cointegrated": bool(johansen["cointegrated"]) if johansen["cointegrated"] is not None else None,
                "upstream": upstream,
                "downstream": downstream,
                "var_lag_aic": int(lag_info["aic"]),
                "johansen_lag": int(johansen_lag),
            }

            row = {
                "commodity_id": commodity_id,
                "segment": segment,
                "upstream": upstream,
                "downstream": downstream,
                "n_obs": n_obs,
                "var_lag_aic": lag_info["aic"],
                "var_lag_bic": lag_info["bic"],
                "johansen_lag": johansen_lag,
                **johansen,
                "model_selected": model,
                "integration_flag": compat["flag"],
            }
            all_results.append(row)

            icon = "✓" if johansen["cointegrated"] else "✗"
            flag_str = f"  {compat['flag']}" if compat["flag"] else ""
            print(f"  구간 {segment:2s} ({upstream:>20s} 에서 {downstream:<20s}) | "
                  f"{icon} {model:4s} | "
                  f"Trace={johansen['trace_stat_r0']} vs {johansen['trace_crit_r0']} | "
                  f"lag={johansen_lag}{flag_str}")

    results_df = pd.DataFrame(all_results)
    results_path = os.path.join(output_dir, "cointegration_results.csv")
    results_df.to_csv(results_path, index=False, encoding="utf-8-sig")

    selection_path = os.path.join(output_dir, "model_routing.json")
    with open(selection_path, "w", encoding="utf-8") as f:
        json.dump(model_selection, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print("Phase 3 완료!")
    print(f"  검정 결과:     {results_path}")
    print(f"  모형 선택:     {selection_path}")
    print(f"{'─' * 60}")

    total = len(results_df)
    if total == 0:
        print("  결과 없음 (입력 데이터 부재)")
        print(f"{'=' * 60}")
        return results_df, model_selection

    vecm_count = len(results_df[results_df["model_selected"] == "VECM"])
    var_count = len(results_df[results_df["model_selected"] == "VAR"])
    flagged = len(results_df[results_df["integration_flag"].notna()])

    print(f"  총 구간 쌍: {total}개")
    print(f"  VECM (공적분 있음): {vecm_count}개")
    print(f"  VAR  (공적분 없음): {var_count}개")
    if flagged > 0:
        print(f"  적분 차수 주의 플래그: {flagged}개")

    print(f"\n{'─' * 60}")
    print("품목별 모형 선택 요약:")
    for cid, segments in model_selection.items():
        seg_str = ", ".join([f"{s}={v['model']}" for s, v in segments.items()])
        print(f"  {cid:12s}: {seg_str}")
    print(f"{'=' * 60}")

    return results_df, model_selection


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    run_phase3()
