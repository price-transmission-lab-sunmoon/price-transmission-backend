"""
Phase 7 통합 -- phase7_summary + stat_timeseries CSV 생성
=========================================================
역할:
  (1) phase7_summary.csv 생성:
      패턴 1/2/3 결과를 품목x구간x월 단위로 통합한다.
      동월/동구간 복수 패턴은 1행으로 집계한다 (D-13 규칙).
      primary_pattern 결정: 심각도 기준 pattern2 > pattern1 > pattern3.
      탐지된 이벤트만 기록한다 (어느 패턴도 flag 없으면 제외).

  (2) stat_timeseries CSV 생성 (33개 구간):
      db_schema_v5의 stat_timeseries 테이블과 1:1 대응하는 형태로,
      전이율/Z-score/IQR/ECT/안정구간/스프레드/환율/달러국제가 등을
      전 시점에 대해 출력한다.

입력 파일:
  - data/processed/product_config.json
  - data/processed/phase3/model_routing.json
  - data/processed/phase1/changes/{cid}_changes.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/phase4/ect/{cid}_{seg}_ect.csv
  - data/processed/phase7/pattern1/{cid}_{seg}_pattern1.csv
  - data/processed/phase7/pattern2/{cid}_{seg}_pattern2_zscore.csv
  - data/processed/phase7/pattern3/{cid}_{seg}_pattern3.csv
  - data/processed/phase7/robustness/{cid}_{seg}_robustness_W36.csv
  - data/processed/phase7/robustness/{cid}_{seg}_robustness_W60.csv

출력 파일:
  - data/processed/phase7/phase7_summary.csv                        (1개)
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


# ---------------------------------------------------------------------------
# phase7_summary.csv 생성
# ---------------------------------------------------------------------------
def build_summary(config, phase7_dir):
    """
    패턴 1/2/3 결과를 통합하여 phase7_summary.csv를 생성한다.

    동월/동구간 복수 패턴은 1행으로 집계한다 (D-13).
    탐지된 이벤트만 기록한다.

    Args:
        config: product_config dict
        phase7_dir: Phase 7 출력 디렉토리 경로

    Returns:
        summary DataFrame
    """
    from pathlib import Path
    phase7 = Path(phase7_dir)

    all_events = []

    for cid, seg in iter_segments(config):
        # 패턴 1 로드
        p1_path = phase7 / "pattern1" / f"{cid}_{seg}_pattern1.csv"
        p1 = pd.read_csv(p1_path)
        p1_flags = p1[p1["pattern1_flag"] == True]

        # 패턴 2 로드 (A, B만)
        p2_flags = pd.DataFrame()
        if seg in PATTERN2_SEGMENTS:
            p2_path = phase7 / "pattern2" / f"{cid}_{seg}_pattern2_zscore.csv"
            p2 = pd.read_csv(p2_path)
            p2_flags = p2[p2["pattern2_flag"] == True]

        # 패턴 3 로드 (B만)
        p3_flags = pd.DataFrame()
        if seg in PATTERN3_SEGMENTS:
            p3_path = phase7 / "pattern3" / f"{cid}_{seg}_pattern3.csv"
            p3 = pd.read_csv(p3_path)
            p3_flags = p3[p3["pattern3_flag"] == True]

        # 전체 탐지 날짜 수집
        all_dates = set()
        for df_flags in [p1_flags, p2_flags, p3_flags]:
            if len(df_flags) > 0:
                all_dates.update(df_flags["date"].values)

        # 날짜별 통합
        for date in sorted(all_dates):
            patterns = []
            flag_details = []

            # 패턴 1 확인
            p1_row = p1_flags[p1_flags["date"] == date]
            if len(p1_row) > 0:
                patterns.append("pattern1")
                flag_details.append(p1_row.iloc[0]["flag_type"])

            # 패턴 2 확인
            if len(p2_flags) > 0:
                p2_row = p2_flags[p2_flags["date"] == date]
                if len(p2_row) > 0:
                    patterns.append("pattern2")
                    if p2_row.iloc[0]["over_transmission"]:
                        flag_details.append("over_transmission")
                    else:
                        flag_details.append("under_transmission")

            # 패턴 3 확인
            if len(p3_flags) > 0:
                p3_row = p3_flags[p3_flags["date"] == date]
                if len(p3_row) > 0:
                    patterns.append("pattern3")
                    flag_details.append("spread_accumulation")

            if len(patterns) == 0:
                continue

            # primary_pattern 결정 (심각도 기준)
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


# ---------------------------------------------------------------------------
# stat_timeseries CSV 생성
# ---------------------------------------------------------------------------
def build_stat_timeseries(paths, config, routing, cid, seg, phase7_dir):
    """
    단일 품목x구간에 대해 stat_timeseries CSV를 생성한다.

    db_schema_v5의 stat_timeseries 테이블 컬럼과 1:1 대응한다.

    Args:
        paths: DataPaths 인스턴스
        config: product_config dict
        routing: model_routing dict
        cid: 품목 ID
        seg: 구간 ID
        phase7_dir: Phase 7 출력 디렉토리 경로

    Returns:
        stat_timeseries DataFrame
    """
    from pathlib import Path
    phase7 = Path(phase7_dir)

    # 기본 데이터 로드
    df = load_changes(paths, cid)
    baseline = load_baseline(paths, cid, seg)
    ect_df = load_ect(paths, cid, seg)
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)
    warmup_end = get_warmup_end(baseline)

    # 전이율 산출
    tr = compute_transmission_rate(df[up_pct_col], df[dn_pct_col])

    # 결과 DataFrame 시작
    result = pd.DataFrame(index=df.index)
    result["commodity_id"] = cid
    result["segment_id"] = seg
    result["period"] = df.index

    # 전이율, 상류/하류 변화율
    result["transmission_rate"] = tr.values
    result["upstream_pct"] = df[up_pct_col].values
    result["downstream_pct"] = df[dn_pct_col].values

    # 패턴 2 Z-score/IQR (A, B 구간만)
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

        # 로버스트니스 W36, W60
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
        # 패턴 2 미적용 구간은 NaN
        for col in ["rolling_mean", "rolling_std", "zscore", "q1", "q3",
                     "iqr", "iqr_lower", "iqr_upper", "zscore_w36", "zscore_w60"]:
            result[col] = np.nan
        result["in_warmup_period"] = df.index <= warmup_end

    # ECT / 로그 스프레드
    result["ect_or_spread"] = ect_df["ect"].values
    result["ect_type"] = ect_df["ect_type"].values

    # 패턴 3 (B 구간만)
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

    # 외생 피처
    result["exchange_rate_pct"] = df["exchange_rate_pct"].values if "exchange_rate_pct" in df.columns else np.nan
    result["intl_price_usd_pct"] = df["intl_price_usd_pct"].values if "intl_price_usd_pct" in df.columns else np.nan

    # 컬럼 순서 정리 (db_schema_v5 stat_timeseries 순서)
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


# ---------------------------------------------------------------------------
# 전체 통합 실행
# ---------------------------------------------------------------------------
def run_integrate(data_dir, output_dir):
    """
    Phase 7 통합을 수행한다.

    (1) phase7_summary.csv 생성
    (2) stat_timeseries CSV 33개 생성

    Args:
        data_dir: 데이터 루트 디렉토리
        output_dir: Phase 7 출력 루트 디렉토리
    """
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    routing = load_model_routing(paths)
    output_base = ensure_output_dirs(output_dir)

    # --- (1) phase7_summary.csv ---
    log("phase7_summary.csv 생성 시작")
    summary = build_summary(config, output_dir)

    summary_path = output_base / "phase7_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # 통계
    total_events = len(summary)
    unique_dates = summary.groupby(["commodity_id", "segment"]).size()
    multi_pattern = summary[summary["pattern_types_all"].str.contains(",")]

    log(f"  총 탐지 이벤트: {total_events}건")
    log(f"  복수 패턴 이벤트: {len(multi_pattern)}건")

    # 패턴별 건수 (primary 기준)
    if total_events > 0:
        by_pattern = summary["pattern_type"].value_counts()
        for pt, cnt in by_pattern.items():
            log(f"    {pt}: {cnt}건 (primary)")

    log(f"  저장: {summary_path}")

    # --- (2) stat_timeseries CSV ---
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
