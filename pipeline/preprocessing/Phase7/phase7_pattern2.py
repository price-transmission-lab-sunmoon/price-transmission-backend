"""
Phase 7 패턴 2 — 전이율 크기 이탈(Z-score+IQR) 및 비대칭 전달(로켓-깃털) 탐지.

Z-score 경보(>= 2.5) + IQR 이탈 동시 충족 시 flag. warmup 48개월 제외.
비대칭 검정: 공적분 있음 → TECM, 없음 → 비대칭 VAR (Wald 검정).
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


def compute_rolling_stats(transmission_rate, window, warmup_end):
    """
    롤링 Z-score + IQR 산출. t시점 판정에 t-1까지만 사용 (look-ahead bias 방지).
    warmup_end 이전은 in_warmup_period=True로 표시하고 탐지 제외.
    """
    n = len(transmission_rate)
    dates = transmission_rate.index
    tr_vals = transmission_rate.values

    rolling_mean = np.full(n, np.nan)
    rolling_std = np.full(n, np.nan)
    zscore = np.full(n, np.nan)
    q1 = np.full(n, np.nan)
    q3 = np.full(n, np.nan)
    iqr = np.full(n, np.nan)
    iqr_lower = np.full(n, np.nan)
    iqr_upper = np.full(n, np.nan)

    for t in range(1, n):
        start_idx = max(0, t - window)
        window_data = tr_vals[start_idx:t]
        valid = window_data[~np.isnan(window_data)]

        if len(valid) < 10:
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

        if std_val > 1e-10 and not np.isnan(tr_vals[t]):
            zscore[t] = (tr_vals[t] - mean_val) / std_val

    zscore_warning_arr = np.abs(zscore) >= ZSCORE_WARNING
    zscore_alert_arr = np.abs(zscore) >= ZSCORE_ALERT
    iqr_outlier_arr = np.zeros(n, dtype=bool)
    for t in range(n):
        if not np.isnan(tr_vals[t]) and not np.isnan(iqr_lower[t]):
            iqr_outlier_arr[t] = (
                tr_vals[t] < iqr_lower[t] or tr_vals[t] > iqr_upper[t]
            )

    in_warmup = np.array([d <= warmup_end for d in dates], dtype=bool)

    # Z-score 경보 + IQR 이탈 + warmup 아님을 동시 충족 시 flag
    pattern2_flag = zscore_alert_arr & iqr_outlier_arr & ~in_warmup

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


def run_tecm_asymmetry(ect_series, changes_df, upstream_pct_col,
                       downstream_pct_col, lag_order):
    """
    TECM 비대칭 검정. ECT 양/음 분리 후 alpha+/alpha- OLS 추정, Wald 검정.
    H0: alpha+ = alpha-.
    """
    common_idx = ect_series.index.intersection(changes_df.index)
    ect = ect_series.loc[common_idx].values
    dy = changes_df.loc[common_idx, downstream_pct_col].values

    # 1기 전 ECT를 양/음으로 분리
    n = len(ect)
    if n < lag_order + 10:
        return _empty_asymmetry_result("TECM", True)

    y = dy[lag_order + 1:]
    ect_lagged = ect[lag_order:-1]

    ect_pos = np.where(ect_lagged > 0, ect_lagged, 0)
    ect_neg = np.where(ect_lagged < 0, ect_lagged, 0)

    X = np.column_stack([ect_pos, ect_neg, np.ones(len(y))])

    valid = ~np.isnan(y) & ~np.isnan(ect_pos) & ~np.isnan(ect_neg)
    if valid.sum() < 10:
        return _empty_asymmetry_result("TECM", True)

    y_valid = y[valid]
    X_valid = X[valid]

    try:
        beta, residuals, rank, sv = np.linalg.lstsq(X_valid, y_valid, rcond=None)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("TECM", True)

    alpha_pos = beta[0]
    alpha_neg = beta[1]

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

    # Wald 검정: R*beta = [alpha+ - alpha-], H0: 0
    R = np.array([[1, -1, 0]])
    r = np.array([0])
    Rb = R @ beta - r
    try:
        wald_stat = float(Rb.T @ np.linalg.inv(R @ cov_beta @ R.T) @ Rb)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("TECM", True)

    p_value = 1 - sp_stats.chi2.cdf(wald_stat, df=1)

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


def run_asymmetric_var(changes_df, upstream_pct_col, downstream_pct_col,
                       lag_order):
    """
    비대칭 VAR 검정. 상승/하락기 더미 교차항 OLS + Wald 검정.
    H0: beta_up = beta_dn.
    """
    up = changes_df[upstream_pct_col].values
    dn = changes_df[downstream_pct_col].values

    n = len(up)
    if n < lag_order + 10:
        return _empty_asymmetry_result("AsymVAR", False)

    y = dn[lag_order + 1:]
    up_lagged = up[lag_order:-1]

    valid = ~np.isnan(y) & ~np.isnan(up_lagged)
    if valid.sum() < 10:
        return _empty_asymmetry_result("AsymVAR", False)

    y_v = y[valid]
    up_v = up_lagged[valid]

    d_up = (up_v > 0).astype(float)
    d_dn = 1 - d_up
    up_pos = up_v * d_up
    up_neg = up_v * d_dn

    X = np.column_stack([up_pos, up_neg, np.ones(len(y_v))])

    try:
        beta, _, _, _ = np.linalg.lstsq(X, y_v, rcond=None)
    except np.linalg.LinAlgError:
        return _empty_asymmetry_result("AsymVAR", False)

    beta_up = beta[0]
    beta_dn = beta[1]

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
    """데이터 부족 시 비대칭 검정 빈 결과 반환."""
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


def compute_mean_tr_by_regime(transmission_rate, upstream_pct):
    """상승기/하락기별 평균 전이율 산출."""
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


def run_pattern2_segment(paths, config, routing, cid, seg):
    """단일 품목x구간에 대해 패턴 2 탐지를 수행한다. 반환: (zscore_df, asymmetry_dict, robustness_dfs)."""
    df = load_changes(paths, cid)
    baseline = load_baseline(paths, cid, seg)
    ect_df = load_ect(paths, cid, seg)
    seg_routing = routing[cid][seg]
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)

    upstream_pct = df[up_pct_col]
    downstream_pct = df[dn_pct_col]
    warmup_end = get_warmup_end(baseline)

    tr = compute_transmission_rate(upstream_pct, downstream_pct)

    stats_df = compute_rolling_stats(tr, ROLLING_WINDOW, warmup_end)

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

    robustness_dfs = {}
    for w in ROLLING_WINDOW_ROBUSTNESS:
        if w == ROLLING_WINDOW:
            continue
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

    lag_order = seg_routing["var_lag_aic"]

    if seg_routing["cointegrated"]:
        asym = run_tecm_asymmetry(
            ect_df["ect"], df, up_pct_col, dn_pct_col, lag_order
        )
    else:
        asym = run_asymmetric_var(
            df, up_pct_col, dn_pct_col, lag_order
        )

    mean_up, mean_dn, n_up, n_dn = compute_mean_tr_by_regime(tr, upstream_pct)
    asym["commodity_id"] = cid
    asym["segment"] = seg
    asym["mean_tr_up"] = round(mean_up, 4) if not np.isnan(mean_up) else np.nan
    asym["mean_tr_down"] = round(mean_dn, 4) if not np.isnan(mean_dn) else np.nan
    asym["n_up"] = n_up
    asym["n_down"] = n_dn

    return zscore_df, asym, robustness_dfs


def run_pattern2(data_dir, output_dir):
    """A/B 구간 20개에 대해 패턴 2 탐지를 수행하고 CSV로 저장한다."""
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

        zs_path = output_base / "pattern2" / f"{cid}_{seg}_pattern2_zscore.csv"
        zscore_df.to_csv(zs_path, index=False, encoding="utf-8-sig")

        for w, rob_df in rob_dfs.items():
            rob_path = (
                output_base / "robustness" / f"{cid}_{seg}_robustness_W{w}.csv"
            )
            rob_df.to_csv(rob_path, index=False, encoding="utf-8-sig")

        asymmetry_results.append(asym)

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

    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern2" / "pattern2_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    asym_df = pd.DataFrame(asymmetry_results)
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
