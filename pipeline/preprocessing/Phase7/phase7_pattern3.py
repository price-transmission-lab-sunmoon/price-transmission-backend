"""
Phase 7 패턴 3 -- 국제가격 안정기 중 하류 물가 스프레드 누적 확대 탐지
====================================================================
역할:
  (1) 국제가 안정 구간 판별:
      원화 환산 국제가 변화율(intl_price_krw_pct) 절대값이 3% 이내인
      기간을 안정 구간으로 정의한다.

  (2) 스프레드 누적 확대 판정 (B안 -- 같은 부호 + 절대값 확대):
      공적분 있는 구간 -> ECT 사용.
      공적분 없는 구간 -> 로그 스프레드 사용.
      ECT/스프레드가 같은 부호를 유지하면서 절대값이 N개월 연속
      증가할 때 탐지한다. 안정 구간 내에서만 판정한다.

  (3) N값 3단계 동시 운용:
      N=2 (조기 신호), N=3 (기본 탐지), N=6 (구조적 이상).

입력 파일:
  - data/processed/product_config.json
  - data/processed/phase3/model_routing.json
  - data/processed/phase1/changes/{cid}_changes.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/phase4/ect/{cid}_{seg}_ect.csv

출력 파일:
  - data/processed/phase7/pattern3/{cid}_{seg}_pattern3.csv  (10개)
  - data/processed/phase7/pattern3/pattern3_summary_stats.csv (1개)

출력 CSV 컬럼:
  date                 : 월 기준일 (YYYY-MM-01)
  commodity_id         : 품목 식별자
  segment              : 구간 (B)
  intl_price_krw_pct   : 원화 환산 국제가 변화율 (%)
  in_stable_period     : 국제가 안정 구간 여부
  ect_or_spread        : ECT 또는 로그 스프레드 값
  ect_type             : ECT / log_spread
  ect_abs              : ECT/스프레드 절대값
  ect_sign             : ECT/스프레드 부호 (+1 / -1 / 0)
  abs_expanding        : 절대값 확대 여부 (직전 대비)
  same_sign_streak     : 같은 부호 유지 연속 개월 수
  abs_expand_streak    : 같은 부호 + 절대값 확대 연속 개월 수
  spread_n2            : N=2 조기 신호 (True/False)
  spread_n3            : N=3 기본 탐지 (True/False)
  spread_n6            : N=6 구조적 이상 (True/False)
  pattern3_flag        : 최종 패턴 3 판정 (= spread_n3, 안정 구간 내에서만)
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


# ---------------------------------------------------------------------------
# 국제가 안정 구간 판별
# ---------------------------------------------------------------------------
def detect_stable_period(intl_price_krw_pct, threshold=STABILITY_THRESHOLD):
    """
    원화 환산 국제가 변화율 절대값이 임계값 이내인 월을 안정 구간으로 판정한다.

    Args:
        intl_price_krw_pct: 국제가 원화 환산 변화율 Series (%, 예: 3.0 = 3%)
        threshold: 안정 구간 임계 (비율, 0.03 = 3%)

    Returns:
        안정 구간 여부 Series (bool)
    """
    # threshold는 비율(0.03)이지만 변화율은 %(3.0)이므로 변환
    threshold_pct = threshold * 100
    stable = intl_price_krw_pct.abs() <= threshold_pct
    # NaN은 안정 구간 아님
    stable = stable.fillna(False)
    return stable


# ---------------------------------------------------------------------------
# 스프레드 누적 확대 판정 (B안: 같은 부호 + 절대값 확대)
# ---------------------------------------------------------------------------
def detect_spread_expansion(ect_values, in_stable, n_values=PATTERN3_N_VALUES):
    """
    ECT/스프레드가 같은 부호를 유지하면서 절대값이 N개월 연속
    확대되는 구간을 탐지한다. 안정 구간 내에서만 판정한다.

    Args:
        ect_values: ECT 또는 로그 스프레드 Series
        in_stable: 안정 구간 여부 Series (bool)
        n_values: N값 리스트 [2, 3, 6]

    Returns:
        DataFrame (ect_abs, ect_sign, abs_expanding, same_sign_streak,
                   abs_expand_streak, spread_n2, spread_n3, spread_n6)
    """
    n = len(ect_values)
    dates = ect_values.index
    vals = ect_values.values
    stable = in_stable.values

    ect_abs = np.abs(vals)
    ect_sign = np.sign(vals)

    # 직전 대비 절대값 확대 여부
    abs_expanding = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if not np.isnan(ect_abs[i]) and not np.isnan(ect_abs[i - 1]):
            abs_expanding[i] = ect_abs[i] > ect_abs[i - 1]

    # 같은 부호 + 절대값 확대 연속 카운트
    same_sign_streak = np.zeros(n, dtype=int)
    abs_expand_streak = np.zeros(n, dtype=int)

    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            same_sign_streak[i] = 0
            abs_expand_streak[i] = 0
            continue

        # 같은 부호 연속
        if ect_sign[i] == ect_sign[i - 1] and ect_sign[i] != 0:
            same_sign_streak[i] = same_sign_streak[i - 1] + 1
        else:
            same_sign_streak[i] = 0

        # 같은 부호 + 절대값 확대 연속
        if (
            ect_sign[i] == ect_sign[i - 1]
            and ect_sign[i] != 0
            and abs_expanding[i]
        ):
            abs_expand_streak[i] = abs_expand_streak[i - 1] + 1
        else:
            abs_expand_streak[i] = 0

    # N값별 판정 (안정 구간 내에서만)
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


# ---------------------------------------------------------------------------
# 패턴 3 단일 구간 실행
# ---------------------------------------------------------------------------
def run_pattern3_segment(paths, config, routing, cid, seg):
    """
    단일 품목x구간에 대해 패턴 3 탐지를 수행한다.

    Returns:
        패턴 3 결과 DataFrame
    """
    # 데이터 로드
    df = load_changes(paths, cid)
    ect_df = load_ect(paths, cid, seg)
    seg_routing = routing[cid][seg]

    # 국제가 안정 구간 판별
    in_stable = detect_stable_period(df["intl_price_krw_pct"])

    # 스프레드 누적 확대 판정
    spread_result = detect_spread_expansion(ect_df["ect"], in_stable)

    # 최종 판정: N=3 기본 탐지를 pattern3_flag로 사용
    pattern3_flag = spread_result["spread_n3"].values

    # 결과 DataFrame 조립 (pipeline_output_spec_v7 컬럼명 기준)
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


# ---------------------------------------------------------------------------
# 패턴 3 전체 실행
# ---------------------------------------------------------------------------
def run_pattern3(data_dir, output_dir):
    """
    B구간 10개에 대해 패턴 3 탐지를 수행하고 CSV로 저장한다.

    Args:
        data_dir: 데이터 루트 디렉토리
        output_dir: Phase 7 출력 루트 디렉토리
    """
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    routing = load_model_routing(paths)
    output_base = ensure_output_dirs(output_dir)

    total = get_segment_count(config, PATTERN3_SEGMENTS)
    log(f"패턴 3 시작: {total}개 구간")

    summary_stats = []

    for cid, seg in iter_segments(config, PATTERN3_SEGMENTS):
        result = run_pattern3_segment(paths, config, routing, cid, seg)

        # CSV 저장
        out_path = output_base / "pattern3" / f"{cid}_{seg}_pattern3.csv"
        result.to_csv(out_path, index=False, encoding="utf-8-sig")

        # 통계 집계
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

    # 요약 통계 저장
    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern3" / "pattern3_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    log(f"패턴 3 완료. 요약: {summary_path}")

    return summary_df


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

    summary = run_pattern3(DATA_DIR, OUTPUT_DIR)
    print()
    print(summary.to_string(index=False))
