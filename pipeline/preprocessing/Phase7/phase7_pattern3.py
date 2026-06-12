"""
Phase 7 패턴 3 — 국제가 안정기 중 하류 스프레드 누적 확대 탐지.

안정 구간: intl_price_krw_pct 절대값 3% 이내.
탐지 기준: 같은 부호 유지 + ECT/스프레드 절대값 N개월 연속 확대.
N=2(조기), N=3(기본 flag), N=6(구조적) 동시 운용.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase7_common import (
    DataPaths,
    load_product_config,
    load_model_routing,
    load_changes,
    load_baseline,
    load_ect,
    get_pct_columns,
    iter_segments,
    get_segment_count,
    ensure_output_dirs,
    log,
    PATTERN3_SEGMENTS,
    STABILITY_THRESHOLD,
    PATTERN3_N_VALUES,
)


def detect_stable_period(intl_price_krw_pct, threshold=STABILITY_THRESHOLD):
    """국제가 변화율 절대값이 threshold(%) 이내인 월을 안정 구간으로 판정. NaN은 비안정."""
    # threshold는 0.03 비율, 변화율 Series는 % 단위이므로 변환
    threshold_pct = threshold * 100
    stable = intl_price_krw_pct.abs() <= threshold_pct
    stable = stable.fillna(False)
    return stable


def detect_spread_expansion(ect_values, in_stable, n_values=PATTERN3_N_VALUES):
    """
    ECT/스프레드가 같은 부호를 유지하며 절대값이 N개월 연속 확대될 때 탐지.
    안정 구간 내에서만 판정한다.
    """
    n = len(ect_values)
    dates = ect_values.index
    vals = ect_values.values
    stable = in_stable.values

    ect_abs = np.abs(vals)
    ect_sign = np.sign(vals)

    abs_expanding = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if not np.isnan(ect_abs[i]) and not np.isnan(ect_abs[i - 1]):
            abs_expanding[i] = ect_abs[i] > ect_abs[i - 1]

    same_sign_streak = np.zeros(n, dtype=int)
    abs_expand_streak = np.zeros(n, dtype=int)

    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            same_sign_streak[i] = 0
            abs_expand_streak[i] = 0
            continue

        if ect_sign[i] == ect_sign[i - 1] and ect_sign[i] != 0:
            same_sign_streak[i] = same_sign_streak[i - 1] + 1
        else:
            same_sign_streak[i] = 0

        if (
            ect_sign[i] == ect_sign[i - 1]
            and ect_sign[i] != 0
            and abs_expanding[i]
        ):
            abs_expand_streak[i] = abs_expand_streak[i - 1] + 1
        else:
            abs_expand_streak[i] = 0

    # 안정 구간 내에서만 N값별 판정
    spread_flags = {}
    for nv in n_values:
        flag = np.zeros(n, dtype=bool)
        for i in range(n):
            if stable[i] and abs_expand_streak[i] >= nv:
                flag[i] = True
        spread_flags[f"spread_n{nv}"] = flag

    result = pd.DataFrame(
        {
            "ect_abs": ect_abs,
            "ect_sign": ect_sign,
            "abs_expanding": abs_expanding,
            "same_sign_streak": same_sign_streak,
            "abs_expand_streak": abs_expand_streak,
        },
        index=dates,
    )

    for key, flag in spread_flags.items():
        result[key] = flag

    return result


def run_pattern3_segment(paths, config, routing, cid, seg):
    """단일 품목x구간에 대해 패턴 3 탐지를 수행한다."""
    df = load_changes(paths, cid)
    ect_df = load_ect(paths, cid, seg)

    in_stable = detect_stable_period(df["intl_price_krw_pct"])
    spread_result = detect_spread_expansion(ect_df["ect"], in_stable)

    # N=3을 최종 flag로 사용
    pattern3_flag = spread_result["spread_n3"].values

    result = pd.DataFrame(
        {
            "date": df.index,
            "commodity_id": cid,
            "segment": seg,
            "intl_pct_change": df["intl_price_krw_pct"].values,
            "in_stable_period": in_stable.values,
            "ect_or_spread": ect_df["ect"].values,
            "ect_type": ect_df["ect_type"].values,
            "ect_abs": spread_result["ect_abs"].values,
            "ect_sign": spread_result["ect_sign"].values,
            "abs_expanding": spread_result["abs_expanding"].values,
            "same_sign_streak": spread_result["same_sign_streak"].values,
            "abs_expand_streak": spread_result["abs_expand_streak"].values,
            "pattern3_flag_n2": spread_result["spread_n2"].values,
            "pattern3_flag_n3": spread_result["spread_n3"].values,
            "pattern3_flag_n6": spread_result["spread_n6"].values,
            "pattern3_flag": pattern3_flag,
        }
    )

    return result


def run_pattern3(data_dir, output_dir):
    """B구간 10개에 대해 패턴 3 탐지를 수행하고 CSV로 저장한다."""
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    routing = load_model_routing(paths)
    output_base = ensure_output_dirs(output_dir)

    total = get_segment_count(config, PATTERN3_SEGMENTS)
    log(f"패턴 3 시작: {total}개 구간")

    summary_stats = []

    for cid, seg in iter_segments(config, PATTERN3_SEGMENTS):
        result = run_pattern3_segment(paths, config, routing, cid, seg)

        out_path = output_base / "pattern3" / f"{cid}_{seg}_pattern3.csv"
        result.to_csv(out_path, index=False, encoding="utf-8-sig")

        n_total = len(result)
        n_stable = result["in_stable_period"].sum()
        n_n2 = result["pattern3_flag_n2"].sum()
        n_n3 = result["pattern3_flag_n3"].sum()
        n_n6 = result["pattern3_flag_n6"].sum()
        n_flag = result["pattern3_flag"].sum()
        ect_type = result["ect_type"].iloc[0]

        summary_stats.append(
            {
                "commodity_id": cid,
                "segment": seg,
                "ect_type": ect_type,
                "total_months": n_total,
                "stable_months": n_stable,
                "stable_pct": round(n_stable / n_total * 100, 1),
                "spread_n2": n_n2,
                "spread_n3": n_n3,
                "spread_n6": n_n6,
                "pattern3_flag": n_flag,
            }
        )

        log(
            f"  {cid:12s} {seg}: "
            f"stable={n_stable:3d}/{n_total} ({n_stable/n_total*100:.0f}%), "
            f"N2={n_n2:3d}, N3={n_n3:3d}, N6={n_n6:3d}, "
            f"flag={n_flag:3d} | {ect_type}"
        )

    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern3" / "pattern3_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    log(f"패턴 3 완료. 요약: {summary_path}")

    return summary_df


if __name__ == "__main__":
    DATA_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed"
    )
    OUTPUT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7"
    )

    summary = run_pattern3(DATA_DIR, OUTPUT_DIR)
    print()
    print(summary.to_string(index=False))
