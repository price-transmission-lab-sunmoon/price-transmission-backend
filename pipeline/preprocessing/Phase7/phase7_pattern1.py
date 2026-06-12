"""
Phase 7 패턴 1 — 가격 전달 방향 역전 및 전달 시차 이탈 탐지.

방향 역전: 상류/하류 변화율 부호 불일치.
시차 이탈: 상류 변동 후 (정상 시차 + 1)개월 내 하류 미반응.
정상 시차는 구조 변화 여부에 따라 하위 기간별 IRF 피크 사용.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase7_common import (
    DataPaths,
    load_product_config,
    load_changes,
    load_baseline,
    get_pct_columns,
    get_warmup_end,
    SubperiodResolver,
    iter_segments,
    get_segment_count,
    ensure_output_dirs,
    log,
    PATTERN1_SEGMENTS,
    DIRECTION_REVERSAL_MIN_MAGNITUDE,
)


def detect_direction_reversal(upstream_pct, downstream_pct,
                              min_magnitude=DIRECTION_REVERSAL_MIN_MAGNITUDE):
    """
    상류/하류 변화율 부호 불일치를 방향 역전으로 판정한다.
    양쪽 모두 min_magnitude 이상이어야 판정 (미세 변동 노이즈 제외).
    """
    reversal = pd.Series(False, index=upstream_pct.index, dtype=bool)

    valid_mask = (
        upstream_pct.notna()
        & downstream_pct.notna()
        & (upstream_pct != 0)
        & (downstream_pct != 0)
        & (upstream_pct.abs() >= min_magnitude)
        & (downstream_pct.abs() >= min_magnitude)
    )

    sign_differs = np.sign(upstream_pct) != np.sign(downstream_pct)
    reversal[valid_mask & sign_differs] = True

    return reversal


def detect_lag_deviation(upstream_pct, downstream_pct, dates, resolver):
    """
    상류 변동 후 (정상 시차 + 1)개월 윈도우 내 하류 미반응을 시차 이탈로 판정한다.
    윈도우가 관측 기간 종료를 넘으면 insufficient_data=True로 판정 유보.
    """
    n = len(dates)
    lag_dev = pd.Series(False, index=dates, dtype=bool)
    insuf = pd.Series(False, index=dates, dtype=bool)
    normal_lags = pd.Series(np.nan, index=dates, dtype=float)
    upstream_move_dates = pd.Series(pd.NaT, index=dates)
    lag_elapsed_arr = pd.Series(np.nan, index=dates, dtype=float)

    up_vals = upstream_pct.values
    dn_vals = downstream_pct.values

    for i in range(n):
        if pd.isna(up_vals[i]) or up_vals[i] == 0:
            continue

        normal_lag = resolver.get_normal_lag(dates[i])
        normal_lags.iloc[i] = normal_lag

        window_end = i + normal_lag + 1  # 정상 시차 + 버퍼 1개월

        if window_end >= n:
            insuf.iloc[i] = True
            continue

        direction = 1 if up_vals[i] > 0 else -1
        responded = False
        for j in range(i + 1, window_end + 1):
            if pd.notna(dn_vals[j]) and dn_vals[j] * direction > 0:
                responded = True
                break

        if not responded:
            lag_dev.iloc[i] = True
            upstream_move_dates.iloc[i] = dates[i]
            lag_elapsed_arr.iloc[i] = normal_lag + 1

    return lag_dev, insuf, normal_lags, upstream_move_dates, lag_elapsed_arr


def run_pattern1_segment(paths, config, cid, seg):
    """단일 품목x구간에 대해 패턴 1 탐지를 수행한다."""
    df = load_changes(paths, cid)
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)

    upstream_pct = df[up_pct_col]
    downstream_pct = df[dn_pct_col]
    dates = df.index

    resolver = SubperiodResolver(paths, cid, seg)

    direction_reversal = detect_direction_reversal(upstream_pct, downstream_pct)

    lag_deviation, insufficient_data, normal_lags, upstream_move_dates, lag_elapsed = (
        detect_lag_deviation(upstream_pct, downstream_pct, dates, resolver)
    )

    subperiod_ids = pd.Series(
        [resolver.get_subperiod_id(d) for d in dates],
        index=dates,
        dtype="Int64",
    )

    # 시차 이탈 미판정 행에도 정상 시차 참고값 채우기
    for i, d in enumerate(dates):
        if pd.isna(normal_lags.iloc[i]):
            normal_lags.iloc[i] = resolver.get_normal_lag(d)

    pattern1_flag = direction_reversal | lag_deviation

    flag_type = pd.Series("none", index=dates, dtype=str)
    mask_both = direction_reversal & lag_deviation
    mask_rev_only = direction_reversal & ~lag_deviation
    mask_lag_only = ~direction_reversal & lag_deviation
    flag_type[mask_both] = "both"
    flag_type[mask_rev_only] = "direction_reversal"
    flag_type[mask_lag_only] = "lag_deviation"

    result = pd.DataFrame(
        {
            "date": dates,
            "commodity_id": cid,
            "segment": seg,
            "upstream_pct": upstream_pct.values,
            "downstream_pct": downstream_pct.values,
            "direction_reversal": direction_reversal.values,
            "upstream_move_date": upstream_move_dates.values,
            "lag_elapsed": lag_elapsed.values,
            "normal_lag": normal_lags.values.astype(int),
            "lag_deviation": lag_deviation.values,
            "insufficient_data": insufficient_data.values,
            "subperiod_id": subperiod_ids.values,
            "pattern1_flag": pattern1_flag.values,
            "flag_type": flag_type.values,
        }
    )

    return result


def run_pattern1(data_dir, output_dir):
    """전 33개 구간에 대해 패턴 1 탐지를 수행하고 CSV로 저장한다."""
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    output_base = ensure_output_dirs(output_dir)

    total = get_segment_count(config, PATTERN1_SEGMENTS)
    log(f"패턴 1 시작: {total}개 구간")

    summary_stats = []

    for cid, seg in iter_segments(config, PATTERN1_SEGMENTS):
        result = run_pattern1_segment(paths, config, cid, seg)

        out_path = output_base / "pattern1" / f"{cid}_{seg}_pattern1.csv"
        result.to_csv(out_path, index=False, encoding="utf-8-sig")

        n_reversal = result["direction_reversal"].sum()
        n_lag_dev = result["lag_deviation"].sum()
        n_insuf = result["insufficient_data"].sum()
        n_flag = result["pattern1_flag"].sum()
        n_total = len(result)

        summary_stats.append(
            {
                "commodity_id": cid,
                "segment": seg,
                "total_months": n_total,
                "direction_reversal": n_reversal,
                "lag_deviation": n_lag_dev,
                "insufficient_data": n_insuf,
                "pattern1_flag": n_flag,
            }
        )

        log(
            f"  {cid:12s} {seg:8s}: "
            f"reversal={n_reversal:3d}, lag_dev={n_lag_dev:3d}, "
            f"insuf={n_insuf:3d}, flag={n_flag:3d} / {n_total}"
        )

    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern1" / "pattern1_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    log(f"패턴 1 완료. 요약: {summary_path}")

    return summary_df


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed")
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7")

    summary = run_pattern1(DATA_DIR, OUTPUT_DIR)
    print()
    print(summary.to_string(index=False))
