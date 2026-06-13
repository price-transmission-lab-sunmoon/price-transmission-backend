"""
Phase 7 통합. phase7_summary.csv 및 stat_timeseries CSV 생성

입력: phase1/4/6/7 패턴 결과, product_config, model_routing
출력:
  - data/processed/phase7/phase7_summary.csv
  - data/processed/phase7/stat_timeseries/{cid}_{seg}_stat_timeseries.csv (33개)
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
    get_warmup_end,
    compute_transmission_rate,
    iter_segments,
    get_segment_count,
    ensure_output_dirs,
    log,
    PATTERN_SEVERITY,
    PATTERN2_SEGMENTS,
    PATTERN3_SEGMENTS,
)


def build_summary(config, phase7_dir):
    """패턴 1/2/3 결과를 품목x구간x월 단위로 통합. 동월 복수 패턴은 1행으로 집계."""
    from pathlib import Path
    phase7 = Path(phase7_dir)

    all_events = []

    for cid, seg in iter_segments(config):
        p1_path = phase7 / "pattern1" / f"{cid}_{seg}_pattern1.csv"
        p1 = pd.read_csv(p1_path)
        p1_flags = p1[p1["pattern1_flag"] == True]

        p2_flags = pd.DataFrame()
        if seg in PATTERN2_SEGMENTS:
            p2_path = phase7 / "pattern2" / f"{cid}_{seg}_pattern2_zscore.csv"
            p2 = pd.read_csv(p2_path)
            p2_flags = p2[p2["pattern2_flag"] == True]

        p3_flags = pd.DataFrame()
        if seg in PATTERN3_SEGMENTS:
            p3_path = phase7 / "pattern3" / f"{cid}_{seg}_pattern3.csv"
            p3 = pd.read_csv(p3_path)
            p3_flags = p3[p3["pattern3_flag"] == True]

        all_dates = set()
        for df_flags in [p1_flags, p2_flags, p3_flags]:
            if len(df_flags) > 0:
                all_dates.update(df_flags["date"].values)

        for date in sorted(all_dates):
            patterns = []
            flag_details = []

            p1_row = p1_flags[p1_flags["date"] == date]
            if len(p1_row) > 0:
                patterns.append("pattern1")
                flag_details.append(p1_row.iloc[0]["flag_type"])

            if len(p2_flags) > 0:
                p2_row = p2_flags[p2_flags["date"] == date]
                if len(p2_row) > 0:
                    patterns.append("pattern2")
                    if p2_row.iloc[0]["over_transmission"]:
                        flag_details.append("over_transmission")
                    else:
                        flag_details.append("under_transmission")

            if len(p3_flags) > 0:
                p3_row = p3_flags[p3_flags["date"] == date]
                if len(p3_row) > 0:
                    patterns.append("pattern3")
                    flag_details.append("spread_accumulation")

            if len(patterns) == 0:
                continue

            # primary_pattern: 심각도 기준 (pattern2 > pattern1 > pattern3)
            primary = max(patterns, key=lambda p: PATTERN_SEVERITY.get(p, 0))

            all_events.append(
                {
                    "date": date,
                    "commodity_id": cid,
                    "segment": seg,
                    "pattern_type": primary,
                    "pattern_types_all": ",".join(sorted(patterns)),
                    "flag_detail": ",".join(flag_details),
                    "stat_detected": True,
                }
            )

    summary = pd.DataFrame(all_events)
    if len(summary) > 0:
        summary = summary.sort_values(["commodity_id", "segment", "date"])
        summary = summary.reset_index(drop=True)

    return summary


def build_stat_timeseries(paths, config, routing, cid, seg, phase7_dir):
    """단일 품목x구간에 대해 stat_timeseries CSV를 생성한다."""
    from pathlib import Path
    phase7 = Path(phase7_dir)

    df = load_changes(paths, cid)
    baseline = load_baseline(paths, cid, seg)
    ect_df = load_ect(paths, cid, seg)
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)
    warmup_end = get_warmup_end(baseline)

    tr = compute_transmission_rate(df[up_pct_col], df[dn_pct_col])

    result = pd.DataFrame(index=df.index)
    result["commodity_id"] = cid
    result["segment_id"] = seg
    result["period"] = df.index
    result["transmission_rate"] = tr.values
    result["upstream_pct"] = df[up_pct_col].values
    result["downstream_pct"] = df[dn_pct_col].values

    if seg in PATTERN2_SEGMENTS:
        p2_path = phase7 / "pattern2" / f"{cid}_{seg}_pattern2_zscore.csv"
        p2 = pd.read_csv(p2_path)
        result["rolling_mean"] = p2["rolling_mean"].values
        result["rolling_std"] = p2["rolling_std"].values
        result["zscore"] = p2["zscore"].values
        result["q1"] = p2["q1"].values
        result["q3"] = p2["q3"].values
        result["iqr"] = p2["iqr"].values
        result["iqr_lower"] = p2["iqr_lower"].values
        result["iqr_upper"] = p2["iqr_upper"].values
        result["in_warmup_period"] = p2["in_warmup_period"].values

        rob36_path = phase7 / "robustness" / f"{cid}_{seg}_robustness_W36.csv"
        rob60_path = phase7 / "robustness" / f"{cid}_{seg}_robustness_W60.csv"
        if rob36_path.exists():
            rob36 = pd.read_csv(rob36_path)
            result["zscore_w36"] = rob36["zscore"].values
        else:
            result["zscore_w36"] = np.nan
        if rob60_path.exists():
            rob60 = pd.read_csv(rob60_path)
            result["zscore_w60"] = rob60["zscore"].values
        else:
            result["zscore_w60"] = np.nan
    else:
        for col in ["rolling_mean", "rolling_std", "zscore", "q1", "q3",
                     "iqr", "iqr_lower", "iqr_upper", "zscore_w36", "zscore_w60"]:
            result[col] = np.nan
        result["in_warmup_period"] = df.index <= warmup_end

    result["ect_or_spread"] = ect_df["ect"].values
    result["ect_type"] = ect_df["ect_type"].values

    if seg in PATTERN3_SEGMENTS:
        p3_path = phase7 / "pattern3" / f"{cid}_{seg}_pattern3.csv"
        p3 = pd.read_csv(p3_path)
        result["in_stable_period"] = p3["in_stable_period"].values
        result["spread_n2"] = p3["pattern3_flag_n2"].values
        result["spread_n3"] = p3["pattern3_flag_n3"].values
        result["spread_n6"] = p3["pattern3_flag_n6"].values
    else:
        result["in_stable_period"] = np.nan
        result["spread_n2"] = np.nan
        result["spread_n3"] = np.nan
        result["spread_n6"] = np.nan

    result["exchange_rate_pct"] = df["exchange_rate_pct"].values if "exchange_rate_pct" in df.columns else np.nan
    result["intl_price_usd_pct"] = df["intl_price_usd_pct"].values if "intl_price_usd_pct" in df.columns else np.nan

    ordered_cols = [
        "commodity_id", "segment_id", "period",
        "transmission_rate", "upstream_pct", "downstream_pct",
        "rolling_mean", "rolling_std", "zscore",
        "q1", "q3", "iqr", "iqr_lower", "iqr_upper",
        "in_warmup_period",
        "zscore_w36", "zscore_w60",
        "ect_or_spread", "ect_type",
        "in_stable_period", "spread_n2", "spread_n3", "spread_n6",
        "exchange_rate_pct", "intl_price_usd_pct",
    ]
    result = result[ordered_cols]
    result = result.reset_index(drop=True)

    return result


def run_integrate(data_dir, output_dir):
    """phase7_summary.csv 및 stat_timeseries CSV 33개를 생성한다."""
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    routing = load_model_routing(paths)
    output_base = ensure_output_dirs(output_dir)

    log("phase7_summary.csv 생성 시작")
    summary = build_summary(config, output_dir)

    summary_path = output_base / "phase7_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    total_events = len(summary)
    multi_pattern = summary[summary["pattern_types_all"].str.contains(",")]

    log(f"  총 탐지 이벤트: {total_events}건")
    log(f"  복수 패턴 이벤트: {len(multi_pattern)}건")

    if total_events > 0:
        by_pattern = summary["pattern_type"].value_counts()
        for pt, cnt in by_pattern.items():
            log(f"    {pt}: {cnt}건 (primary)")

    log(f"  저장: {summary_path}")

    total_seg = get_segment_count(config)
    log(f"stat_timeseries 생성 시작: {total_seg}개 구간")

    for cid, seg in iter_segments(config):
        st = build_stat_timeseries(paths, config, routing, cid, seg, output_dir)

        st_path = (
            output_base / "stat_timeseries" / f"{cid}_{seg}_stat_timeseries.csv"
        )
        st.to_csv(st_path, index=False, encoding="utf-8-sig")

        log(f"  {cid:12s} {seg:8s}: {len(st)} rows")

    log("Phase 7 통합 완료")

    return summary


if __name__ == "__main__":
    DATA_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed"
    )
    OUTPUT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7"
    )

    summary = run_integrate(DATA_DIR, OUTPUT_DIR)

    print()
    print("=== phase7_summary 통계 ===")
    if len(summary) > 0:
        print(f"총 이벤트: {len(summary)}")
        print()
        print("패턴별 (primary):")
        print(summary["pattern_type"].value_counts().to_string())
        print()
        print("품목별:")
        print(summary.groupby("commodity_id").size().to_string())
        print()
        print("복수 패턴 이벤트:")
        multi = summary[summary["pattern_types_all"].str.contains(",")]
        if len(multi) > 0:
            print(multi["pattern_types_all"].value_counts().to_string())
        else:
            print("  없음")
