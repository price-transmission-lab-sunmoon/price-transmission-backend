"""
Phase 4 — 모형 추정 및 기준선 산출 (VAR/VECM + IRF)

목적:
    Phase 3의 모형 선택 결과(model_routing.json)에 따라 구간별로
    VAR 또는 VECM을 추정하고, IRF에서 정상 전달 시차와 전이탄력성을 산출한다.
    ECT(VECM) 또는 로그 수준 스프레드(VAR)도 함께 산출하여 Phase 7 입력으로 제공한다.

입력:
    data/processed/phase1/seasonal_adjusted/{cid}_sa.csv   — 수준 데이터 (VECM용)
    data/processed/phase1/changes/{cid}_changes.csv        — 변화율 데이터 (VAR용)
    data/processed/phase3/model_routing.json               — 구간별 모형 선택
    data/processed/product_config.json                     — 품목별 설정

출력:
    data/processed/phase4/model_params/{cid}_{seg}_model.json   — 추정 모형 파라미터
    data/processed/phase4/irf/{cid}_{seg}_irf.csv               — IRF 시계열 + CI
    data/processed/phase4/baseline/{cid}_{seg}_baseline.json    — 기준선 테이블
    data/processed/phase4/ect/{cid}_{seg}_ect.csv               — ECT 또는 로그 스프레드
    data/processed/phase4/phase4_summary.csv                    — 전 품목·구간 추정 요약

실행:
    python src/preprocessing/phase4_model_estimation.py

작성일: 2026-04-22
"""

import os
import json
import warnings
import pandas as pd
import numpy as np
from statsmodels.tsa.api import VAR
from statsmodels.tsa.vector_ar.vecm import VECM
from dateutil.relativedelta import relativedelta

# ──────────────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SA_DIR = os.path.join(BASE_DIR, "data", "processed", "phase1", "seasonal_adjusted")
CHANGES_DIR = os.path.join(BASE_DIR, "data", "processed", "phase1", "changes")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "processed", "product_config.json")
ROUTING_PATH = os.path.join(BASE_DIR, "data", "processed", "phase3", "model_routing.json")
PHASE4_DIR = os.path.join(BASE_DIR, "data", "processed", "phase4")

# ──────────────────────────────────────────────
# 파라미터
# ──────────────────────────────────────────────
IRF_HORIZON = 24            # IRF 산출 기간 (개월)
ROLLING_WINDOW = 48         # warmup_end 산출용 롤링 윈도우
VECM_DET = "ci"             # VECM deterministic: 'ci' = 상수항 in cointegrating relation
VECM_COINT_RANK = 1         # 공적분 벡터 수 (2변수 시스템에서 최대 1)


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_sa_data(commodity_id: str) -> pd.DataFrame:
    path = os.path.join(SA_DIR, f"{commodity_id}_sa.csv")
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


def load_changes_data(commodity_id: str) -> pd.DataFrame:
    path = os.path.join(CHANGES_DIR, f"{commodity_id}_changes.csv")
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


# ──────────────────────────────────────────────
# VECM 추정
# ──────────────────────────────────────────────
def estimate_vecm(pair_sa: pd.DataFrame, lag: int) -> dict:
    """
    VECM 추정. 수준(level) 데이터 입력.

    Returns: model_fit, ect_series, irf_data, model_info
    """
    vecm = VECM(pair_sa, k_ar_diff=lag, coint_rank=VECM_COINT_RANK,
                deterministic=VECM_DET)
    fit = vecm.fit()

    # ECT 산출: beta' * Y_t
    beta = fit.beta          # (2, 1) 공적분 벡터
    ect_values = pair_sa.values @ beta  # (T, 1)
    ect_series = pd.Series(ect_values[:, 0], index=pair_sa.index, name="ect")

    # IRF 산출
    irf_obj = fit.irf(periods=IRF_HORIZON)
    irf_values = irf_obj.irfs[:, 1, 0]  # downstream response to upstream shock

    # stderr 기반 95% CI
    try:
        irf_stderr = irf_obj.stderr()[:, 1, 0]
        irf_lower = irf_values - 1.96 * irf_stderr
        irf_upper = irf_values + 1.96 * irf_stderr
    except Exception:
        irf_lower = np.full_like(irf_values, np.nan)
        irf_upper = np.full_like(irf_values, np.nan)

    # 피크 산출
    peak_horizon = int(np.argmax(np.abs(irf_values)))
    peak_magnitude = float(irf_values[peak_horizon])

    irf_data = {
        "horizon": list(range(IRF_HORIZON + 1)),
        "irf_downstream": irf_values.tolist(),
        "irf_lower_ci": irf_lower.tolist(),
        "irf_upper_ci": irf_upper.tolist(),
        "peak_horizon": peak_horizon,
        "peak_magnitude": peak_magnitude,
    }

    model_info = {
        "model_type": "VECM",
        "lag_selected": lag,
        "n_obs": len(pair_sa),
        "cointegrated": True,
        "det_order": 0,
        "coint_rank": VECM_COINT_RANK,
        "alpha": fit.alpha.tolist(),
        "beta": fit.beta.tolist(),
    }

    return {
        "fit": fit,
        "ect_series": ect_series,
        "ect_type": "ECT",
        "irf_data": irf_data,
        "model_info": model_info,
    }


# ──────────────────────────────────────────────
# VAR 추정
# ──────────────────────────────────────────────
def estimate_var(pair_changes: pd.DataFrame, pair_sa: pd.DataFrame, lag: int) -> dict:
    """
    VAR 추정. 변화율(차분) 데이터 입력.
    로그 수준 스프레드는 수준 데이터에서 산출.

    Returns: model_fit, spread_series, irf_data, model_info
    """
    pair_clean = pair_changes.dropna()
    var_model = VAR(pair_clean)
    fit = var_model.fit(lag)

    # 로그 수준 스프레드: log(downstream_sa) - log(upstream_sa)
    upstream_col = pair_sa.columns[0]
    downstream_col = pair_sa.columns[1]

    # 안전한 로그 변환 (0 이하 값 처리)
    upstream_safe = pair_sa[upstream_col].clip(lower=1e-10)
    downstream_safe = pair_sa[downstream_col].clip(lower=1e-10)
    log_spread = np.log(downstream_safe) - np.log(upstream_safe)
    log_spread.name = "ect"

    # IRF 산출
    irf_obj = fit.irf(periods=IRF_HORIZON)
    irf_values = irf_obj.irfs[:, 1, 0]

    # stderr 기반 95% CI
    try:
        irf_stderr = irf_obj.stderr()[:, 1, 0]
        irf_lower = irf_values - 1.96 * irf_stderr
        irf_upper = irf_values + 1.96 * irf_stderr
    except Exception:
        irf_lower = np.full_like(irf_values, np.nan)
        irf_upper = np.full_like(irf_values, np.nan)

    # 피크 산출
    peak_horizon = int(np.argmax(np.abs(irf_values)))
    peak_magnitude = float(irf_values[peak_horizon])

    irf_data = {
        "horizon": list(range(IRF_HORIZON + 1)),
        "irf_downstream": irf_values.tolist(),
        "irf_lower_ci": irf_lower.tolist(),
        "irf_upper_ci": irf_upper.tolist(),
        "peak_horizon": peak_horizon,
        "peak_magnitude": peak_magnitude,
    }

    model_info = {
        "model_type": "VAR",
        "lag_selected": lag,
        "n_obs": int(fit.nobs),
        "cointegrated": False,
        "det_order": None,
        "coint_rank": None,
        "aic": float(fit.aic),
        "bic": float(fit.bic),
    }

    return {
        "fit": fit,
        "ect_series": log_spread,
        "ect_type": "log_spread",
        "irf_data": irf_data,
        "model_info": model_info,
    }


# ──────────────────────────────────────────────
# 산출물 저장
# ──────────────────────────────────────────────
def save_model_params(commodity_id: str, segment: str, route: dict,
                      model_info: dict, output_dir: str):
    """모형 파라미터 JSON 저장"""
    params = {
        "commodity_id": commodity_id,
        "segment": segment,
        "upstream_col": route["upstream"],
        "downstream_col": route["downstream"],
        "lag_selection_criterion": "AIC",
        **model_info,
    }
    path = os.path.join(output_dir, "model_params", f"{commodity_id}_{segment}_model.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)


def save_irf(commodity_id: str, segment: str, irf_data: dict, output_dir: str):
    """IRF CSV 저장"""
    df = pd.DataFrame({
        "horizon": irf_data["horizon"],
        "irf_downstream": irf_data["irf_downstream"],
        "irf_lower_ci": irf_data["irf_lower_ci"],
        "irf_upper_ci": irf_data["irf_upper_ci"],
    })
    # 피크 정보는 모든 행에 동일하게 기록
    df["irf_peak_horizon"] = irf_data["peak_horizon"]
    df["irf_peak_magnitude"] = irf_data["peak_magnitude"]

    path = os.path.join(output_dir, "irf", f"{commodity_id}_{segment}_irf.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")


def save_baseline(commodity_id: str, segment: str, route: dict,
                  model_info: dict, irf_data: dict,
                  estimation_start: str, estimation_end: str,
                  output_dir: str):
    """기준선 JSON 저장"""
    # warmup_end = estimation_start + 48개월
    start_dt = pd.Timestamp(estimation_start)
    warmup_end_dt = start_dt + relativedelta(months=ROLLING_WINDOW)
    warmup_end = warmup_end_dt.strftime("%Y-%m")

    baseline = {
        "commodity_id": commodity_id,
        "segment": segment,
        "normal_transmission_lag": irf_data["peak_horizon"],
        "transmission_elasticity": round(irf_data["peak_magnitude"], 6),
        "warmup_end": warmup_end,
        "model_type": model_info["model_type"],
        "estimation_period_start": estimation_start,
        "estimation_period_end": estimation_end,
        "n_obs": model_info["n_obs"],
    }
    path = os.path.join(output_dir, "baseline", f"{commodity_id}_{segment}_baseline.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)


def save_ect(commodity_id: str, segment: str, ect_series: pd.Series,
             ect_type: str, output_dir: str):
    """ECT/로그 스프레드 CSV 저장"""
    df = pd.DataFrame({
        "ect": ect_series.values,
        "ect_type": ect_type,
    }, index=ect_series.index)
    df.index.name = "date"

    path = os.path.join(output_dir, "ect", f"{commodity_id}_{segment}_ect.csv")
    df.to_csv(path, encoding="utf-8-sig")


# ──────────────────────────────────────────────
# 통합 실행
# ──────────────────────────────────────────────
def run_phase4(sa_dir: str = SA_DIR,
               changes_dir: str = CHANGES_DIR,
               config_path: str = CONFIG_PATH,
               routing_path: str = ROUTING_PATH,
               output_dir: str = PHASE4_DIR):
    """Phase 4 전체 파이프라인 실행"""

    # 출력 디렉토리 생성
    for sub in ["model_params", "irf", "baseline", "ect"]:
        os.makedirs(os.path.join(output_dir, sub), exist_ok=True)

    config = load_json(config_path)
    routing = load_json(routing_path)
    summary_rows = []

    print("=" * 60)
    print("Phase 4 — 모형 추정 및 기준선 산출 (VAR/VECM + IRF)")
    print("=" * 60)

    for commodity_id, cfg in config.items():
        print(f"\n{'─' * 40}")
        print(f"[{commodity_id}] {cfg['name_kr']} ({cfg['name_en']})")

        df_sa = load_sa_data(commodity_id)
        df_changes = load_changes_data(commodity_id)

        for segment, route in routing[commodity_id].items():
            upstream = route["upstream"]
            downstream = route["downstream"]
            model_type = route["model"]
            lag = route["johansen_lag"] if model_type == "VECM" else route["var_lag_aic"]

            # 데이터 준비
            upstream_sa = f"{upstream}_sa"
            downstream_sa = f"{downstream}_sa"
            pair_sa = df_sa[[upstream_sa, downstream_sa]].dropna()

            estimation_start = pair_sa.index[0].strftime("%Y-%m")
            estimation_end = pair_sa.index[-1].strftime("%Y-%m")

            try:
                if model_type == "VECM":
                    result = estimate_vecm(pair_sa, lag)
                else:  # VAR
                    upstream_pct = f"{upstream}_pct"
                    downstream_pct = f"{downstream}_pct"
                    pair_changes = df_changes[[upstream_pct, downstream_pct]].dropna()
                    result = estimate_var(pair_changes, pair_sa, lag)

                # 산출물 저장
                save_model_params(commodity_id, segment, route,
                                  result["model_info"], output_dir)
                save_irf(commodity_id, segment, result["irf_data"], output_dir)
                save_baseline(commodity_id, segment, route,
                              result["model_info"], result["irf_data"],
                              estimation_start, estimation_end, output_dir)
                save_ect(commodity_id, segment, result["ect_series"],
                         result["ect_type"], output_dir)

                # 요약 행
                irf = result["irf_data"]
                summary_rows.append({
                    "commodity_id": commodity_id,
                    "segment": segment,
                    "model_type": model_type,
                    "lag": lag,
                    "n_obs": result["model_info"]["n_obs"],
                    "peak_horizon": irf["peak_horizon"],
                    "peak_magnitude": round(irf["peak_magnitude"], 6),
                    "ect_type": result["ect_type"],
                    "estimation_start": estimation_start,
                    "estimation_end": estimation_end,
                })

                icon = "✓"
                print(f"  구간 {segment:7s} | {icon} {model_type:4s} lag={lag} | "
                      f"IRF peak: {irf['peak_horizon']}개월, "
                      f"탄력성={irf['peak_magnitude']:.6f} | "
                      f"ECT: {result['ect_type']}")

            except Exception as e:
                print(f"  구간 {segment:7s} | ✗ 추정 실패: {e}")
                summary_rows.append({
                    "commodity_id": commodity_id,
                    "segment": segment,
                    "model_type": model_type,
                    "lag": lag,
                    "n_obs": len(pair_sa),
                    "peak_horizon": None,
                    "peak_magnitude": None,
                    "ect_type": None,
                    "estimation_start": estimation_start,
                    "estimation_end": estimation_end,
                })

    # ── 요약 저장 ──
    summary_df = pd.DataFrame(summary_rows)
    summary_path = os.path.join(output_dir, "phase4_summary.csv")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # ── 요약 출력 ──
    print(f"\n{'=' * 60}")
    print("Phase 4 완료!")
    print(f"  모형 파라미터: {output_dir}/model_params/")
    print(f"  IRF 시계열:    {output_dir}/irf/")
    print(f"  기준선:        {output_dir}/baseline/")
    print(f"  ECT/스프레드:  {output_dir}/ect/")
    print(f"  요약 리포트:   {summary_path}")
    print(f"{'─' * 60}")

    # 통계
    success = summary_df[summary_df["peak_horizon"].notna()]
    vecm_n = len(success[success["model_type"] == "VECM"])
    var_n = len(success[success["model_type"] == "VAR"])
    fail_n = len(summary_df) - len(success)

    print(f"  총 구간 쌍: {len(summary_df)}개")
    print(f"  VECM 추정 성공: {vecm_n}개")
    print(f"  VAR 추정 성공: {var_n}개")
    if fail_n > 0:
        print(f"  추정 실패: {fail_n}개 ⚠️")

    # IRF 피크 요약
    print(f"\n{'─' * 60}")
    print("IRF 피크 (정상 전달 시차) 요약:")
    for _, row in success.iterrows():
        print(f"  {row['commodity_id']:12s} {row['segment']:7s} | "
              f"{row['model_type']:4s} | 피크={row['peak_horizon']:2.0f}개월 | "
              f"탄력성={row['peak_magnitude']:.6f}")

    print(f"{'=' * 60}")

    return summary_df


# ──────────────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    run_phase4()
