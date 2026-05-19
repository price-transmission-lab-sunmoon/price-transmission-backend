"""
Phase 7 패턴 1 -- 가격 전달 방향 역전 및 전달 시차 이탈 탐지
=============================================================
역할:
  (1) 방향 역전: 매월 상류/하류 변화율 부호를 비교하여 부호가
      다른 달을 기록한다.
  (2) 시차 이탈: 상류 변동 발생 후 (정상 시차 + 버퍼 1개월) 이내에
      하류가 같은 방향으로 한 번이라도 반응했는지를 확인한다.
      한 번도 반응하지 않았으면 시차 이탈로 판정한다.
  (3) 정상 시차는 구조 변화 유무에 따라 하위 기간별 IRF 피크를 사용한다.

입력 파일:
  - data/processed/product_config.json
  - data/processed/phase3/model_routing.json
  - data/processed/phase1/changes/{cid}_changes.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/phase6/breakpoints/{cid}_{seg}_breakpoints.json
  - data/processed/phase6/subperiod_models/{cid}_{seg}_subperiod_{n}_model.json

출력 파일:
  - data/processed/phase7/pattern1/{cid}_{seg}_pattern1.csv  (33개)

출력 CSV 컬럼:
  date                 : 월 기준일 (YYYY-MM-01)
  commodity_id         : 품목 식별자
  segment              : 구간 (A, B, C, D, D_prime)
  upstream_pct         : 상류 변화율 (%)
  downstream_pct       : 하류 변화율 (%)
  direction_reversal   : 방향 역전 여부 (True/False)
  lag_deviation        : 시차 이탈 여부 (True/False)
  insufficient_data    : 시차 이탈 판정 불가 여부 (데이터 끝 잘림)
  normal_lag_months    : 해당 시점의 정상 전달 시차 (개월)
  subperiod_id         : 해당 시점의 하위 기간 ID (구조 변화 없으면 null)
  pattern1_flag        : 최종 패턴 1 판정 (direction_reversal OR lag_deviation)
  flag_type            : 판정 유형 (direction_reversal / lag_deviation / both / none)
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


# ---------------------------------------------------------------------------
# 방향 역전 판정
# ---------------------------------------------------------------------------
def detect_direction_reversal(upstream_pct, downstream_pct,
                              min_magnitude=DIRECTION_REVERSAL_MIN_MAGNITUDE):
    """
    매월 상류/하류 변화율의 부호를 비교하여 방향 역전을 판정한다.

    판정 조건:
      - 양쪽 모두 유효값(NaN 아님)이고 0이 아닐 때
      - 상류와 하류의 부호가 다르고
      - 양쪽 모두 변화율 절대값이 min_magnitude(%) 이상일 때

    노이즈 수준의 미세 변동(예: +0.1% vs -0.2%)은 방향 역전으로
    판정하지 않는다. 가격 전달 시차가 존재하는 상황에서 동시점
    부호 비교만으로는 과다 탐지가 발생하기 때문이다.

    Args:
        upstream_pct: 상류 변화율 Series
        downstream_pct: 하류 변화율 Series
        min_magnitude: 방향 역전 판정을 위한 최소 변동 크기 (%, 기본 1.0)

    Returns:
        방향 역전 여부 Series (bool)
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


# ---------------------------------------------------------------------------
# 시차 이탈 판정
# ---------------------------------------------------------------------------
def detect_lag_deviation(upstream_pct, downstream_pct, dates, resolver):
    """
    상류 변동 발생 후 (정상 시차 + 1)개월 내에 하류가 같은 방향으로
    한 번이라도 반응했는지를 확인하여 시차 이탈을 판정한다.

    판정 로직:
      1. 매월 상류 변화율이 0이 아니면 "상류 변동 이벤트"로 인식한다.
      2. 해당 시점의 정상 전달 시차를 SubperiodResolver에서 조회한다.
      3. 이후 (정상 시차 + 1)개월 윈도우 내에서 하류가 같은 방향으로
         한 번이라도 반응했으면 "반응함", 한 번도 없으면 "시차 이탈".
      4. 윈도우가 관측 기간 종료 시점을 넘으면 판정 유보(insufficient_data).

    Args:
        upstream_pct: 상류 변화율 Series (DatetimeIndex)
        downstream_pct: 하류 변화율 Series (DatetimeIndex)
        dates: DatetimeIndex
        resolver: SubperiodResolver 인스턴스

    Returns:
        (lag_deviation, insufficient_data, normal_lag, upstream_move_date, lag_elapsed)
        각각 Series.
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
        # 상류 NaN이거나 0이면 변동 이벤트 아님
        if pd.isna(up_vals[i]) or up_vals[i] == 0:
            continue

        # 정상 시차 조회 (하위 기간별)
        normal_lag = resolver.get_normal_lag(dates[i])
        normal_lags.iloc[i] = normal_lag

        window_end = i + normal_lag + 1  # 정상 시차 + 버퍼 1개월

        # 관측 기간 종료 시점을 넘으면 판정 유보
        if window_end >= n:
            insuf.iloc[i] = True
            continue

        # 윈도우 내에서 같은 방향 반응 확인
        direction = 1 if up_vals[i] > 0 else -1
        responded = False
        for j in range(i + 1, window_end + 1):
            if pd.notna(dn_vals[j]) and dn_vals[j] * direction > 0:
                responded = True
                break

        if not responded:
            lag_dev.iloc[i] = True
            upstream_move_dates.iloc[i] = dates[i]
            lag_elapsed_arr.iloc[i] = normal_lag + 1  # 경과 개월 수 = 윈도우 전체

    return lag_dev, insuf, normal_lags, upstream_move_dates, lag_elapsed_arr


# ---------------------------------------------------------------------------
# 패턴 1 단일 구간 실행
# ---------------------------------------------------------------------------
def run_pattern1_segment(paths, config, cid, seg):
    """
    단일 품목x구간에 대해 패턴 1 탐지를 수행한다.

    Returns:
        패턴 1 결과 DataFrame
    """
    # 데이터 로드
    df = load_changes(paths, cid)
    _, _, up_pct_col, dn_pct_col = get_pct_columns(config, cid, seg)

    upstream_pct = df[up_pct_col]
    downstream_pct = df[dn_pct_col]
    dates = df.index

    # SubperiodResolver 초기화
    resolver = SubperiodResolver(paths, cid, seg)

    # (1) 방향 역전
    direction_reversal = detect_direction_reversal(upstream_pct, downstream_pct)

    # (2) 시차 이탈
    lag_deviation, insufficient_data, normal_lags, upstream_move_dates, lag_elapsed = (
        detect_lag_deviation(upstream_pct, downstream_pct, dates, resolver)
    )

    # (3) subperiod_id 산출
    subperiod_ids = pd.Series(
        [resolver.get_subperiod_id(d) for d in dates],
        index=dates,
        dtype="Int64",
    )

    # 정상 시차: 시차 이탈 판정하지 않은 행에도 참고값 채우기
    for i, d in enumerate(dates):
        if pd.isna(normal_lags.iloc[i]):
            normal_lags.iloc[i] = resolver.get_normal_lag(d)

    # (4) 최종 판정
    pattern1_flag = direction_reversal | lag_deviation

    # (5) flag_type 산출
    flag_type = pd.Series("none", index=dates, dtype=str)
    mask_both = direction_reversal & lag_deviation
    mask_rev_only = direction_reversal & ~lag_deviation
    mask_lag_only = ~direction_reversal & lag_deviation
    flag_type[mask_both] = "both"
    flag_type[mask_rev_only] = "direction_reversal"
    flag_type[mask_lag_only] = "lag_deviation"

    # 결과 DataFrame 조립 (pipeline_output_spec_v7 컬럼명 기준)
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


# ---------------------------------------------------------------------------
# 패턴 1 전체 실행
# ---------------------------------------------------------------------------
def run_pattern1(data_dir, output_dir):
    """
    전 33개 구간에 대해 패턴 1 탐지를 수행하고 CSV로 저장한다.

    Args:
        data_dir: 데이터 루트 디렉토리 (product_config.json 위치)
        output_dir: Phase 7 출력 루트 디렉토리
    """
    paths = DataPaths(data_dir)
    config = load_product_config(paths)
    output_base = ensure_output_dirs(output_dir)

    total = get_segment_count(config, PATTERN1_SEGMENTS)
    log(f"패턴 1 시작: {total}개 구간")

    summary_stats = []

    for cid, seg in iter_segments(config, PATTERN1_SEGMENTS):
        result = run_pattern1_segment(paths, config, cid, seg)

        # CSV 저장
        out_path = output_base / "pattern1" / f"{cid}_{seg}_pattern1.csv"
        result.to_csv(out_path, index=False, encoding="utf-8-sig")

        # 통계 집계
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

    # 요약 통계 저장
    summary_df = pd.DataFrame(summary_stats)
    summary_path = output_base / "pattern1" / "pattern1_summary_stats.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    log(f"패턴 1 완료. 요약: {summary_path}")

    return summary_df


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed")
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed", "phase7")

    summary = run_pattern1(DATA_DIR, OUTPUT_DIR)
    print()
    print(summary.to_string(index=False))
