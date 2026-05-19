"""
Phase 7 패턴 2 -- 전이율 크기 이탈 및 비대칭 전달(로켓-깃털 효과) 탐지
=====================================================================
역할:
  (1) Z-score + IQR 교차 판정:
      롤링 48개월 윈도우로 전이율의 Z-score와 IQR을 산출한다.
      t시점 판정에는 t-1까지의 데이터만 사용하여 미래 정보 유출을 방지한다.
      Z-score >= 2.5(경보) AND IQR 이탈을 동시 충족할 때 최종 경보를 확정한다.
      최초 48개월(warmup)은 기준 분포 축적 기간으로 탐지를 수행하지 않는다.

  (2) 로버스트니스 체크:
      W=36, W=60으로 Z-score를 재산출하여 탐지 민감도를 비교한다.

  (3) 비대칭 검정:
      공적분 있는 구간 -> TECM: ECT를 양/음 분리, alpha+/alpha- 추정, Wald 검정.
      공적분 없는 구간 -> 비대칭 VAR: 상승/하락기 더미 교차항 OLS.
      전체 기간 1회 수행.

입력 파일:
  - data/processed/product_config.json
  - data/processed/phase3/model_routing.json
  - data/processed/phase1/changes/{cid}_changes.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/phase4/ect/{cid}_{seg}_ect.csv

출력 파일:
  - data/processed/phase7/pattern2/{cid}_{seg}_pattern2_zscore.csv   (20개)
  - data/processed/phase7/pattern2/{cid}_{seg}_pattern2_asymmetry.csv (20개)
  - data/processed/phase7/pattern2/pattern2_summary_stats.csv         (1개)
  - data/processed/phase7/robustness/{cid}_{seg}_robustness_W36.csv  (20개)
  - data/processed/phase7/robustness/{cid}_{seg}_robustness_W60.csv  (20개)

출력 CSV 컬럼 (pattern2_zscore):
  date, commodity_id, segment,
  upstream_pct, downstream_pct, transmission_rate,
  rolling_mean, rolling_std, zscore,
  q1, q3, iqr, iqr_lower, iqr_upper,
  zscore_warning, zscore_alert, iqr_outlier,
  pattern2_flag, deviation_type, in_warmup_period

출력 CSV 컬럼 (pattern2_asymmetry):
  commodity_id, segment, method, cointegrated,
  alpha_positive, alpha_negative, test_statistic, p_value,
  asymmetry_significant, asymmetry_direction,
  mean_tr_up, mean_tr_down, n_up, n_down
"""

import sys
import os
import pandas as pd
import numpy as np
from scipy import stats as sp_stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase7_common import (
    DataPaths,
    load_product_config,
    load_model_routing,
    load_changes,
    load_baseline,
    load_ect,
    get_pct_columns,
    get_warmup_end,
    compute_transmission_rate,
    iter_segments,
    get_segment_count,
    ensure_output_dirs,
    log,
    PATTERN2_SEGMENTS,
    ROLLING_WINDOW,
    ROLLING_WINDOW_ROBUSTNESS,
    ZSCORE_WARNING,
    ZSCORE_ALERT,
    IQR_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# 롤링 Z-score + IQR 산출
# ---------------------------------------------------------------------------
def compute_rolling_stats(transmission_rate, window, warmup_end):
    """
    롤링 윈도우 기반으로 Z-score와 IQR 통계를 산출한다.

    t시점 판정에는 t-1까지의 데이터만 사용한다 (look-ahead bias 방지).
    전이율이 NaN인 달은 롤링 통계에서 자동 제외된다.
    warmup_end 이전은 in_warmup_period=True로 표시하고 탐지하지 않는다.

    Args:
        transmission_rate: 전이율 Series (NaN 포함)
        window: 롤링 윈도우 크기 (개월)
        warmup_end: warmup 종료 Timestamp

    Returns:
        DataFrame (rolling_mean, rolling_std, zscore, q1, q3, iqr,
                   iqr_lower, iqr_upper, zscore_warning, zscore_alert,
                   iqr_outlier, pattern2_flag, deviation_type, in_warmup_period)
    """
    n = len(transmission_rate)
    dates = transmission_rate.index
    tr_vals = transmission_rate.values

    # 결과 배열 초기화
    rolling_mean = np.full(n, np.nan)
    rolling_std = np.full(n, np.nan)
    zscore = np.full(n, np.nan)
    q1 = np.full(n, np.nan)
    q3 = np.full(n, np.nan)
    iqr = np.full(n, np.nan)
    iqr_lower = np.full(n, np.nan)
    iqr_upper = np.full(n, np.nan)

    for t in range(1, n):
        # t-1까지의 윈도우에서 유효값 추출
        start_idx = max(0, t - window)
        window_data = tr_vals[start_idx:t]
        valid = window_data[~np.isnan(window_data)]

        if len(valid) < 10:
            # 유효값이 10개 미만이면 통계 산출 불가
            continue

        mean_val = np.mean(valid)
        std_val = np.std(valid, ddof=1)

        rolling_mean[t] = mean_val
        rolling_std[t] = std_val

        q1_val = np.percentile(valid, 25)
        q3_val = np.percentile(valid, 75)
        iqr_val = q3_val - q1_val

        q1[t] = q1_val
        q3[t] = q3_val
        iqr[t] = iqr_val
        iqr_lower[t] = q1_val - IQR_MULTIPLIER * iqr_val
        iqr_upper[t] = q3_val + IQR_MULTIPLIER * iqr_val

        # Z-score 산출
        if std_val > 1e-10 and not np.isnan(tr_vals[t]):
            zscore[t] = (tr_vals[t] - mean_val) / std_val

    # 판정
    zscore_warning_arr = np.abs(zscore) >= ZSCORE_WARNING
    zscore_alert_arr = np.abs(zscore) >= ZSCORE_ALERT
    iqr_outlier_arr = np.zeros(n, dtype=bool)
    for t in range(n):
        if not np.isnan(tr_vals[t]) and not np.isnan(iqr_lower[t]):
            iqr_outlier_arr[t] = (
                tr_vals[t] < iqr_lower[t] or tr_vals[t] > iqr_upper[t]
            )

    # warmup 판정
    in_warmup = np.array([d <= warmup_end for d in dates], dtype=bool)

    # 최종 판정: Z-score 경보 AND IQR 이탈 AND warmup 아님
    pattern2_flag = zscore_alert_arr & iqr_outlier_arr & ~in_warmup

    # 이탈 방향 (bool 분리 - pipeline_output_spec_v7 기준)
    over_transmission = pattern2_flag & (tr_vals > rolling_mean)
    under_transmission = pattern2_flag & (tr_vals <= rolling_mean)

    result = pd.DataFrame(
        {
            "rolling_mean": rolling_mean,
            "rolling_std": rolling_std,
            "zscore": zscore,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "iqr_lower": iqr_lower,
            "iqr_upper": iqr_upper,
            "zscore_warning": zscore_warning_arr,
            "zscore_alert": zscore_alert_arr,
            "iqr_outlier": iqr_outlier_arr,
            "pattern2_flag": pattern2_flag,
            "over_transmission": over_transmission,
            "under_transmission": under_transmission,
            "in_warmup_period": in_warmup,
        },
        index=dates,
    )

    return result


# ---------------------------------------------------------------------------
# 비대칭 검정 -- TECM (공적분 있는 구간)
# ---------------------------------------------------------------------------
def run_tecm_asymmetry(ect_series, changes_df, upstream_pct_col,
                       downstream_pct_col, lag_order):
    """
    Threshold ECM 비대칭 검정을 수행한다.

    ECT를 양수/음수로 분리하여 오차수정 계수(alpha+, alpha-)를 추정하고,
    Wald 검정으로 alpha+ = alpha- 귀무가설을 검정한다.

    Args:
        ect_series: ECT 시계열 Series
        changes_df: 변화율 DataFrame
        upstream_pct_col: 상류 변화율 컬럼명
        downstream_pct_col: 하류 변화율 컬럼명
        lag_order: VAR/VECM 시차

    Returns:
        dict (alpha_positive, alpha_negative, test_statistic, p_value,
              asymmetry_significant, asymmetry_direction)
    """
    # 공통 인덱스 정렬
    common_idx = ect_series.index.intersection(changes_df.index)
    ect = ect_series.loc[common_idx].values
    dy = changes_df.loc[common_idx, downstream_pct_col].values

    # ECT를 양/음으로 분리 (1기 전 ECT 사용)
    n = len(ect)
    if n < lag_order + 10:
        return _empty_asymmetry_result("TECM", True)

    # 종속변수: dy_t, 독립변수: ECT+_{t-1}, ECT-_{t-1}, 시차항
    y = dy[lag_order + 1:]
    ect_lagged = ect[lag_order:-1]

    ect_pos = np.where(ect_lagged > 0, ect_lagged, 0)
    ect_neg = np.where(ect_lagged < 0, ect_lagged, 0)

    # 설계 행렬: [ECT+, ECT-, 상수]
    X = np.column_stack([ect_pos, ect_neg, np.ones(len(y))])

    # 유효값 필터
    valid = ~np.isnan(y) & ~np.isnan(ect_pos) & ~np.isnan(ect_neg)
    if valid.sum() < 10:
        return _empty_asymmetry_result("TECM", True)

    y_valid = y[valid]
    X_valid = X[valid]

    # OLS 추정
    try:
        beta, residuals, rank, sv = np.linalg.lstsq(X_valid, y_valid, rcond=None)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("TECM", True)

    alpha_pos = beta[0]
    alpha_neg = beta[1]

    # Wald 검정: H0: alpha+ = alpha-
    n_obs = len(y_valid)
    k = X_valid.shape[1]
    if n_obs <= k:
        return _empty_asymmetry_result("TECM", True)

    y_hat = X_valid @ beta
    resid = y_valid - y_hat
    sigma2 = np.sum(resid ** 2) / (n_obs - k)

    try:
        cov_beta = sigma2 * np.linalg.inv(X_valid.T @ X_valid)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("TECM", True)

    # R*beta = r, R = [1, -1, 0], r = 0
    R = np.array([[1, -1, 0]])
    r = np.array([0])
    Rb = R @ beta - r
    try:
        wald_stat = float(Rb.T @ np.linalg.inv(R @ cov_beta @ R.T) @ Rb)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("TECM", True)

    p_value = 1 - sp_stats.chi2.cdf(wald_stat, df=1)

    # 비대칭 방향 판단 (pipeline_output_spec_v7 기준 값)
    direction = None
    if p_value < 0.05:
        if abs(alpha_pos) > abs(alpha_neg):
            direction = "upward_stronger"
        else:
            direction = "downward_stronger"

    return {
        "model_type": "TECM",
        "alpha_plus": round(alpha_pos, 6),
        "alpha_minus": round(alpha_neg, 6),
        "wald_stat": round(wald_stat, 4),
        "wald_pvalue": round(p_value, 4),
        "asymmetry_significant": p_value < 0.05,
        "rocket_feather_direction": direction,
        "up_coef": None,
        "down_coef": None,
    }


# ---------------------------------------------------------------------------
# 비대칭 검정 -- 비대칭 VAR (공적분 없는 구간)
# ---------------------------------------------------------------------------
def run_asymmetric_var(changes_df, upstream_pct_col, downstream_pct_col,
                       lag_order):
    """
    비대칭 VAR 검정을 수행한다.

    상승기/하락기 더미 변수(D_t = 1 if upstream_pct > 0, else 0)를
    교차항으로 포함시켜 국면별 전이 계수 차이를 검정한다.

    Args:
        changes_df: 변화율 DataFrame
        upstream_pct_col: 상류 변화율 컬럼명
        downstream_pct_col: 하류 변화율 컬럼명
        lag_order: VAR 시차

    Returns:
        dict (alpha_positive, alpha_negative, test_statistic, p_value,
              asymmetry_significant, asymmetry_direction)
    """
    up = changes_df[upstream_pct_col].values
    dn = changes_df[downstream_pct_col].values

    n = len(up)
    if n < lag_order + 10:
        return _empty_asymmetry_result("AsymVAR", False)

    # 종속변수: dn_t, 독립변수: up_{t-1}*D, up_{t-1}*(1-D), 상수
    y = dn[lag_order + 1:]
    up_lagged = up[lag_order:-1]

    # 유효값 필터
    valid = ~np.isnan(y) & ~np.isnan(up_lagged)
    if valid.sum() < 10:
        return _empty_asymmetry_result("AsymVAR", False)

    y_v = y[valid]
    up_v = up_lagged[valid]

    # 상승기/하락기 분리
    d_up = (up_v > 0).astype(float)
    d_dn = 1 - d_up

    up_pos = up_v * d_up   # 상승기 상류 변화율
    up_neg = up_v * d_dn   # 하락기 상류 변화율

    X = np.column_stack([up_pos, up_neg, np.ones(len(y_v))])

    # OLS 추정
    try:
        beta, _, _, _ = np.linalg.lstsq(X, y_v, rcond=None)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("AsymVAR", False)

    beta_up = beta[0]   # 상승기 전이 계수
    beta_dn = beta[1]   # 하락기 전이 계수

    # Wald 검정: H0: beta_up = beta_dn
    n_obs = len(y_v)
    k = X.shape[1]
    if n_obs <= k:
        return _empty_asymmetry_result("AsymVAR", False)

    y_hat = X @ beta
    resid = y_v - y_hat
    sigma2 = np.sum(resid ** 2) / (n_obs - k)

    try:
        cov_beta = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("AsymVAR", False)

    R = np.array([[1, -1, 0]])
    r = np.array([0])
    Rb = R @ beta - r
    try:
        wald_stat = float(Rb.T @ np.linalg.inv(R @ cov_beta @ R.T) @ Rb)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("AsymVAR", False)

    p_value = 1 - sp_stats.chi2.cdf(wald_stat, df=1)

    direction = None
    if p_value < 0.05:
        if abs(beta_up) > abs(beta_dn):
            direction = "upward_stronger"
        else:
            direction = "downward_stronger"

    return {
        "model_type": "asymmetric_VAR",
        "alpha_plus": None,
        "alpha_minus": None,
        "wald_stat": round(wald_stat, 4),
        "wald_pvalue": round(p_value, 4),
        "asymmetry_significant": p_value < 0.05,
        "rocket_feather_direction": direction,
        "up_coef": round(beta_up, 6),
        "down_coef": round(beta_dn, 6),
    }


def _empty_asymmetry_result(method, cointegrated):
    """데이터 부족 시 비대칭 검정 빈 결과를 반환한다."""
    model_type = "TECM" if method == "TECM" else "asymmetric_VAR"
    return {
        "model_type": model_type,
        "alpha_plus": np.nan,
        "alpha_minus": np.nan,
        "wald_stat": np.nan,
        "wald_pvalue": np.nan,
        "asymmetry_significant": False,
        "rocket_feather_direction": None,
        "up_coef": np.nan if not cointegrated else None,
        "down_coef": np.nan if not cointegrated else None,
    }


# ---------------------------------------------------------------------------
# 보조: 전이율 상승기/하락기 평균 (단순 비교용)
# ---------------------------------------------------------------------------
def compute_mean_tr_by_regime(transmission_rate, upstream_pct):
    """상승기/하락기별 평균 전이율을 산출한다."""
    valid = transmission_rate.notna() & upstream_pct.notna()
    tr_v = transmission_rate[valid]
    up_v = upstream_pct[valid]

    up_mask = up_v > 0
    dn_mask = up_v < 0

    mean_up = tr_v[up_mask].mean() if up_mask.sum() > 0 else np.nan
    mean_dn = tr_v[dn_mask].mean() if dn_mask.sum() > 0 else np.nan
    n_up = int(up_mask.sum())
    n_dn = int(dn_mask.sum())

    return mean_up, mean_dn, n_up, n_dn


# ---------------------------------------------------------------------------
# 패턴 2 단일 구간 실행
# ---------------------------------------------------------------------------
def run_pattern2_segment(paths, config, routing, cid, seg):
    """
    단일 품목x구간에 대해 패턴 2 탐지를 수행한다.

    Returns:
        (zscore_df, asymmetry_dict, robustness_dfs)
    """
    # 데이터 로드
    df = load_changes(paths, cid)
    baseline = load_baseline(paths, cid, seg)
    ect_df = load_ect(paths, cid, seg)
    seg_routing = routing[cid][seg]
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)

    upstream_pct = df[up_pct_col]
    downstream_pct = df[dn_pct_col]
    warmup_end = get_warmup_end(baseline)

    # 전이율 산출
    tr = compute_transmission_rate(upstream_pct, downstream_pct)

    # --- (1) Z-score + IQR (기본 윈도우 W=48) ---
    stats_df = compute_rolling_stats(tr, ROLLING_WINDOW, warmup_end)

    # 기본 컬럼 추가
    zscore_df = pd.DataFrame(
        {
            "date": df.index,
            "commodity_id": cid,
            "segment": seg,
            "upstream_pct": upstream_pct.values,
            "downstream_pct": downstream_pct.values,
            "transmission_rate": tr.values,
        }
    )
    for col in stats_df.columns:
        zscore_df[col] = stats_df[col].values

    # --- (2) 로버스트니스 (W=36, W=60) ---
    robustness_dfs = {}
    for w in ROLLING_WINDOW_ROBUSTNESS:
        if w == ROLLING_WINDOW:
            continue  # 기본 윈도우는 이미 산출
        rob_stats = compute_rolling_stats(tr, w, warmup_end)
        rob_df = pd.DataFrame(
            {
                "date": df.index,
                "commodity_id": cid,
                "segment": seg,
                "transmission_rate": tr.values,
                "zscore": rob_stats["zscore"].values,
                "pattern2_flag": rob_stats["pattern2_flag"].values,
                "in_warmup_period": rob_stats["in_warmup_period"].values,
            }
        )
        robustness_dfs[w] = rob_df

    # --- (3) 비대칭 검정 ---
    lag_order = seg_routing["var_lag_aic"]

    if seg_routing["cointegrated"]:
        asym = run_tecm_asymmetry(
            ect_df["ect"], df, up_pct_col, dn_pct_col, lag_order
        )
    else:
        asym = run_asymmetric_var(
            df, up_pct_col, dn_pct_col, lag_order
        )

    # 보조: 상승/하락기 평균 전이율
    mean_up, mean_dn, n_up, n_dn = compute_mean_tr_by_regime(tr, upstream_pct)
    asym["commodity_id"] = cid
    asym["segment"] = seg
    asym["mean_tr_up"] = round(mean_up, 4) if not np.isnan(mean_up) else np.nan
    asym["mean_tr_down"] = round(mean_dn, 4) if not np.isnan(mean_dn) else np.nan
    asym["n_up"] = n_up
    asym["n_down"] = n_dn

    return zscore_df, asym, robustness_dfs


# ---------------------------------------------------------------------------
# 패턴 2 전체 실행
# ---------------------------------------------------------------------------
def run_pattern2(data_dir, output_dir):
    """
    A, B 구간 20개에 대해 패턴 2 탐지를 수행하고 CSV로 저장한다.

    Args:
        data_dir: 데이터 루트 디렉토리
        output_dir: Phase 7 출력 루트 디렉토리
    """
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    routing = load_model_routing(paths)
    output_base = ensure_output_dirs(output_dir)

    total = get_segment_count(config, PATTERN2_SEGMENTS)
    log(f"패턴 2 시작: {total}개 구간")

    summary_stats = []
    asymmetry_results = []

    for cid, seg in iter_segments(config, PATTERN2_SEGMENTS):
        zscore_df, asym, rob_dfs = run_pattern2_segment(
            paths, config, routing, cid, seg
        )

        # Z-score CSV 저장
        zs_path = output_base / "pattern2" / f"{cid}_{seg}_pattern2_zscore.csv"
        zscore_df.to_csv(zs_path, index=False, encoding="utf-8-sig")

        # 로버스트니스 CSV 저장
        for w, rob_df in rob_dfs.items():
            rob_path = (
                output_base / "robustness" / f"{cid}_{seg}_robustness_W{w}.csv"
            )
            rob_df.to_csv(rob_path, index=False, encoding="utf-8-sig")

        # 비대칭 결과 수집
        asymmetry_results.append(asym)

        # 통계 집계
        not_warmup = ~zscore_df["in_warmup_period"]
        n_total = len(zscore_df)
        n_warmup = zscore_df["in_warmup_period"].sum()
        n_flag = zscore_df["pattern2_flag"].sum()
        n_warning = (zscore_df["zscore_warning"] & not_warmup).sum()
        n_alert = (zscore_df["zscore_alert"] & not_warmup).sum()
        n_iqr = (zscore_df["iqr_outlier"] & not_warmup).sum()
        n_over = zscore_df["over_transmission"].sum()
        n_under = zscore_df["under_transmission"].sum()
        tr_nan = zscore_df["transmission_rate"].isna().sum()

        summary_stats.append(
            {
                "commodity_id": cid,
                "segment": seg,
                "total_months": n_total,
                "warmup_months": n_warmup,
                "tr_nan_count": tr_nan,
                "zscore_warning": n_warning,
                "zscore_alert": n_alert,
                "iqr_outlier": n_iqr,
                "pattern2_flag": n_flag,
                "over_transmission": n_over,
                "under_transmission": n_under,
            }
        )

        # 로버스트니스 요약
        rob_flags = {ROLLING_WINDOW: n_flag}
        for w, rob_df in rob_dfs.items():
            rob_not_warmup = ~rob_df["in_warmup_period"]
            rob_flags[w] = (rob_df["pattern2_flag"] & rob_not_warmup).sum()

        rob_str = ", ".join(
            [f"W{w}={c}" for w, c in sorted(rob_flags.items())]
        )

        log(
            f"  {cid:12s} {seg}: "
            f"flag={n_flag:3d}, warn={n_warning:3d}, "
            f"over={n_over:2d}, under={n_under:2d}, "
            f"tr_nan={tr_nan:3d} | "
            f"asym p={asym['wald_pvalue']} ({asym['rocket_feather_direction']}) | "
            f"{rob_str}"
        )

    # 요약 저장
    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern2" / "pattern2_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # 비대칭 검정 결과 저장
    asym_df = pd.DataFrame(asymmetry_results)
    # 컬럼 순서 정리 (pipeline_output_spec_v7 기준)
    asym_cols = [
        "commodity_id", "segment", "model_type",
        "alpha_plus", "alpha_minus",
        "wald_stat", "wald_pvalue",
        "asymmetry_significant", "rocket_feather_direction",
        "up_coef", "down_coef",
        "mean_tr_up", "mean_tr_down", "n_up", "n_down",
    ]
    asym_df = asym_df[asym_cols]
    for cid_seg_row in asym_df.itertuples():
        cid_val = cid_seg_row.commodity_id
        seg_val = cid_seg_row.segment
        row_df = asym_df[
            (asym_df["commodity_id"] == cid_val) & (asym_df["segment"] == seg_val)
        ]
        asym_path = (
            output_base / "pattern2"
            / f"{cid_val}_{seg_val}_pattern2_asymmetry.csv"
        )
        row_df.to_csv(asym_path, index=False, encoding="utf-8-sig")

    log(f"패턴 2 완료. 요약: {summary_path}")

    return summary_df, asym_df


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    DATA_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed"
    )
    OUTPUT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7"
    )

    summary_df, asym_df = run_pattern2(DATA_DIR, OUTPUT_DIR)

    print()
    print("=== Z-score + IQR 요약 ===")
    print(summary_df.to_string(index=False))
    print()
    print("=== 비대칭 검정 결과 ===")
    print(asym_df.to_string(index=False))
