"""
Phase 6 — 구조 변화 탐지 및 기간 분할

목적:
    전이율 시계열에서 Bai-Perron(Dynp+BIC) 방식으로 구조 변화 시점을 자동 탐지하고,
    Chow Test(2008·2020·2022)로 교차 확인한다.
    탐지된 변화 시점을 기준으로 하위 기간을 분할하고,
    각 하위 기간에서 VAR/VECM을 재추정하여 기간별 기준선을 산출한다.

입력:
    phase1/changes/{cid}_changes.csv       — 변화율 데이터 (전이율 산출)
    phase1/seasonal_adjusted/{cid}_sa.csv  — 수준 데이터 (하위 기간 재추정용)
    phase3/model_routing.json              — 구간별 모형 유형·시차
    phase4/baseline/{cid}_{seg}_baseline.json — 전체 기간 기준선
    product_config.json                    — 품목별 설정

출력:
    phase6/breakpoints/{cid}_{seg}_breakpoints.json   — 변화 시점 + 하위 기간
    phase6/chow_results/{cid}_{seg}_chow.csv          — Chow Test 결과
    phase6/subperiod_models/{cid}_{seg}_subperiod_{n}_model.json — 하위 기간 재추정
    phase6/phase6_summary.csv                          — 전 품목·구간 요약

실행:
    python src/preprocessing/phase6_structural_breaks.py

작성일: 2026-04-27
"""

import json
import logging
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import ruptures as rpt
from scipy import stats

# Phase 4 추정 함수 재사용
try:
    from phase4_model_estimation import estimate_vecm, estimate_var
except ImportError:
    from pipeline.preprocessing.phase4_model_estimation import estimate_vecm, estimate_var

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
SIGNIFICANCE_LEVEL = 0.05
STABILITY_THRESHOLD = 0.03       # |상류 변화율| < 3% → 전이율 NaN (Phase 7 동일)
MIN_SUBPERIOD_OBS = 60           # 하위 기간 최소 관측치
MAX_BREAKPOINTS = 5              # Bai-Perron 최대 탐색 변화점 수
CHOW_TEST_POINTS = ["2008-01", "2020-01", "2022-01"]  # 고정 3개 시점

# 경계 사례 구간 — Trace가 임계값 ±10% 이내이거나 모형 전환이 발생한 구간
# Phase 3 결과 기반, 하위기간 재추정 결과에 주의 플래그 부착
BORDERLINE_SEGMENTS = {
    ("groundnuts", "D"),   # Trace=15.55 vs 임계값 15.49 (차이 0.06)
    ("maize", "D_prime"),  # 14개월 추가로 VECM→VAR 뒤집힘
    ("coffee", "B"),       # Trace=14.73 (임계값 대비 95%)
    ("coffee", "A"),       # VAR→VECM 전환 + I(2) 플래그
    ("groundnuts", "B"),   # I(2) 플래그 (땅콩 ppi)
    ("groundnuts", "C"),   # I(2) 플래그 (땅콩 ppi)
}

# 경로 설정
BASE_DIR = Path("data/processed")
CHANGES_DIR = BASE_DIR / "phase1" / "changes"
SA_DIR = BASE_DIR / "phase1" / "seasonal_adjusted"
PHASE3_DIR = BASE_DIR / "phase3"
PHASE4_DIR = BASE_DIR / "phase4"
PHASE6_DIR = BASE_DIR / "phase6"
PRODUCT_CONFIG_PATH = BASE_DIR / "product_config.json"
MODEL_ROUTING_PATH = PHASE3_DIR / "model_routing.json"

# 로깅
logging.basicConfig(
    level=logging.INFO,
    format='{"ts": "%(asctime)s", "level": "%(levelname)s", "code": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────
def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_changes(cid, changes_dir=CHANGES_DIR):
    path = changes_dir / f"{cid}_changes.csv"
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


def load_sa(cid, sa_dir=SA_DIR):
    path = sa_dir / f"{cid}_sa.csv"
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index)
    df.index.freq = "MS"
    return df


# ──────────────────────────────────────────────
# 전이율 산출
# ──────────────────────────────────────────────
def compute_transmission_rate(df_changes, upstream_pct, downstream_pct):
    """
    전이율 = 하류 변화율 / 상류 변화율
    안정 구간 필터: |상류 변화율| < STABILITY_THRESHOLD*100 → NaN
    NaN은 forward-fill 후 남은 선두 NaN은 backward-fill
    극단값 클리핑: ±10 범위 제한
    """
    upstream = df_changes[upstream_pct].copy()
    downstream = df_changes[downstream_pct].copy()

    # 안정 구간 필터: 상류 변화율이 너무 작으면 전이율 정의 불가
    # _pct 컬럼은 %단위 (예: 3.0 = 3%)
    mask_stable = upstream.abs() < (STABILITY_THRESHOLD * 100)
    rate = downstream / upstream
    rate[mask_stable] = np.nan

    # 극단값 클리핑: ±10 범위 제한 (전이율 10배 초과는 노이즈)
    rate = rate.clip(-10, 10)

    # forward-fill → backward-fill
    rate = rate.ffill().bfill()

    # 첫 행 NaN (변화율 자체가 NaN인 경우) 처리
    rate = rate.dropna()

    return rate


# ──────────────────────────────────────────────
# Bai-Perron (Dynp + BIC)
# ──────────────────────────────────────────────
def compute_bic(signal, breakpoints):
    """
    BIC = n * ln(RSS/n) + k * ln(n)
    k = 세그먼트 수 (각 세그먼트의 평균 파라미터) + 변화점 수
    """
    n = len(signal)
    segments = [0] + breakpoints
    rss = 0.0
    n_segments = 0

    for i in range(len(segments) - 1):
        start = segments[i]
        end = segments[i + 1]
        seg = signal[start:end]
        if len(seg) > 0:
            rss += np.sum((seg - np.mean(seg)) ** 2)
            n_segments += 1

    # 파라미터 수: 각 세그먼트 평균 + 분산 + 변화점 위치
    k = 2 * n_segments + (len(breakpoints) - 1)
    if rss <= 0:
        rss = 1e-10

    bic = n * np.log(rss / n) + k * np.log(n)
    return bic


def run_bai_perron(rate_series, min_size=None):
    """
    Dynp + BIC로 최적 변화점 수 및 위치 탐지.

    Returns:
        breakpoint_indices: 변화 시점 인덱스 리스트
        best_k: 최적 변화점 수
        bic_scores: {k: bic} 딕셔너리
    """
    if min_size is None:
        min_size = MIN_SUBPERIOD_OBS

    signal = rate_series.values.reshape(-1, 1)
    n = len(signal)

    # min_size가 n/2보다 크면 분할 불가능
    if n < min_size * 2:
        logger.info(
            'BP_SKIP", "msg": "관측치 부족으로 Bai-Perron 스킵 (n=%d, min_size=%d)"',
            n, min_size,
        )
        return [], 0, {}

    algo = rpt.Dynp(model="normal", min_size=min_size).fit(signal)

    bic_scores = {}
    best_bic = np.inf
    best_k = 0
    best_bkps = [n]  # k=0: 변화점 없음

    # k=0 BIC
    bic_0 = compute_bic(signal.flatten(), [n])
    bic_scores[0] = bic_0
    best_bic = bic_0

    # k=1 ~ MAX_BREAKPOINTS 탐색
    max_possible_k = min(MAX_BREAKPOINTS, (n // min_size) - 1)
    for k in range(1, max_possible_k + 1):
        try:
            bkps = algo.predict(n_bkps=k)
            bic_k = compute_bic(signal.flatten(), bkps)
            bic_scores[k] = bic_k

            if bic_k < best_bic:
                best_bic = bic_k
                best_k = k
                best_bkps = bkps
        except Exception as e:
            logger.warning(
                'BP_WARN", "msg": "Dynp k=%d 실패: %s"', k, str(e)
            )
            break

    # 마지막 원소(=n)는 ruptures 규약이므로 제거
    breakpoint_indices = best_bkps[:-1] if best_k > 0 else []

    return breakpoint_indices, best_k, bic_scores


# ──────────────────────────────────────────────
# Chow Test
# ──────────────────────────────────────────────
def chow_test(rate_series, break_date_str):
    """
    Chow Test: 특정 시점에서의 구조 변화 검정.
    전이율 시계열을 break_date 기준으로 양분, 회귀 계수 변화를 F검정.
    H0: 두 기간의 회귀 계수(상수+시간추세)가 동일하다.
    """
    break_date = pd.Timestamp(f"{break_date_str}-01")

    # 분석 범위 밖 체크
    if break_date < rate_series.index[0] or break_date > rate_series.index[-1]:
        return {
            "break_point": break_date_str,
            "f_stat": None,
            "pvalue": None,
            "significant": None,
            "note": "분석 범위 밖",
        }

    # 양분
    before = rate_series[rate_series.index < break_date]
    after = rate_series[rate_series.index >= break_date]

    if len(before) < 10 or len(after) < 10:
        return {
            "break_point": break_date_str,
            "f_stat": None,
            "pvalue": None,
            "significant": None,
            "note": f"구간 관측치 부족 (전={len(before)}, 후={len(after)})",
        }

    n1, n2 = len(before), len(after)
    n = n1 + n2
    k = 2  # 파라미터 수 (상수 + 시간 추세)

    # 전체 RSS
    X_full = np.column_stack([np.ones(n), np.arange(n)])
    y_full = rate_series.values
    beta_full = np.linalg.lstsq(X_full, y_full, rcond=None)[0]
    rss_full = np.sum((y_full - X_full @ beta_full) ** 2)

    # 전반 RSS
    X1 = np.column_stack([np.ones(n1), np.arange(n1)])
    y1 = before.values
    beta1 = np.linalg.lstsq(X1, y1, rcond=None)[0]
    rss1 = np.sum((y1 - X1 @ beta1) ** 2)

    # 후반 RSS
    X2 = np.column_stack([np.ones(n2), np.arange(n2)])
    y2 = after.values
    beta2 = np.linalg.lstsq(X2, y2, rcond=None)[0]
    rss2 = np.sum((y2 - X2 @ beta2) ** 2)

    # F 통계량
    rss_unrestricted = rss1 + rss2
    df_num = k
    df_den = n - 2 * k

    if df_den <= 0 or rss_unrestricted <= 0:
        return {
            "break_point": break_date_str,
            "f_stat": None,
            "pvalue": None,
            "significant": None,
            "note": "자유도 부족",
        }

    f_stat = ((rss_full - rss_unrestricted) / df_num) / (rss_unrestricted / df_den)
    p_value = 1 - stats.f.cdf(f_stat, df_num, df_den)

    return {
        "break_point": break_date_str,
        "f_stat": round(float(f_stat), 4),
        "pvalue": round(float(p_value), 4),
        "significant": bool(p_value < SIGNIFICANCE_LEVEL),
    }


# ──────────────────────────────────────────────
# 하위 기간 분할 및 병합
# ──────────────────────────────────────────────
def build_subperiods(rate_series, breakpoint_indices):
    """
    변화 시점을 기준으로 하위 기간 분할.
    MIN_SUBPERIOD_OBS 미만인 기간은 인접 기간과 병합.
    """
    dates = rate_series.index
    n = len(dates)

    if len(breakpoint_indices) == 0:
        return [{
            "id": 1,
            "start": dates[0].strftime("%Y-%m"),
            "end": dates[-1].strftime("%Y-%m"),
            "n_obs": n,
        }]

    # 경계 인덱스 → 날짜 변환
    boundaries = [0] + breakpoint_indices + [n]
    raw_subperiods = []

    for i in range(len(boundaries) - 1):
        s_idx = boundaries[i]
        e_idx = min(boundaries[i + 1] - 1, n - 1)

        raw_subperiods.append({
            "id": i + 1,
            "start": dates[s_idx].strftime("%Y-%m"),
            "end": dates[e_idx].strftime("%Y-%m"),
            "n_obs": boundaries[i + 1] - boundaries[i],
        })

    # 병합: MIN_SUBPERIOD_OBS 미만 → 직전 기간에 흡수
    result = []
    for sp in raw_subperiods:
        if sp["n_obs"] < MIN_SUBPERIOD_OBS and len(result) > 0:
            prev = result[-1]
            prev["end"] = sp["end"]
            prev["n_obs"] += sp["n_obs"]
            sp["merged_with"] = prev["id"]
            result.append(sp)
        else:
            result.append(sp)

    # 독립 기간 재번호
    idx = 1
    for sp in result:
        if "merged_with" not in sp:
            sp["id"] = idx
            idx += 1

    return result


# ──────────────────────────────────────────────
# 하위 기간 재추정
# ──────────────────────────────────────────────
def reestimate_subperiod(
    df_sa, df_changes, route, subperiod, output_dir, cid, seg, sp_idx
):
    """
    하위 기간에서 VAR/VECM 재추정.
    Phase 4의 estimate_vecm/estimate_var를 재사용.
    """
    start = pd.Timestamp(f"{subperiod['start']}-01")
    end = pd.Timestamp(f"{subperiod['end']}-01")

    upstream = route["upstream"]
    downstream = route["downstream"]
    model_type = route["model"]
    lag = route["johansen_lag"] if model_type == "VECM" else route["var_lag_aic"]

    upstream_sa = f"{upstream}_sa"
    downstream_sa = f"{downstream}_sa"
    pair_sa = df_sa[[upstream_sa, downstream_sa]].loc[start:end].dropna()

    if len(pair_sa) < MIN_SUBPERIOD_OBS:
        logger.warning(
            'PL-P6-004", "msg": "하위 기간 관측치 부족 (%d < %d)", '
            '"phase": "6", "context": {"commodity_id": "%s", "segment": "%s", '
            '"subperiod_index": %d}',
            len(pair_sa), MIN_SUBPERIOD_OBS, cid, seg, sp_idx,
        )
        return None

    try:
        # 하위 기간이 짧으면 시차 축소
        effective_lag = min(lag, max(1, len(pair_sa) // 10 - 1))

        if model_type == "VECM":
            result = estimate_vecm(pair_sa, effective_lag)
        else:
            upstream_pct = f"{upstream}_pct"
            downstream_pct = f"{downstream}_pct"
            pair_changes = df_changes[[upstream_pct, downstream_pct]].loc[start:end].dropna()
            result = estimate_var(pair_changes, pair_sa, effective_lag)

        # 모형 파라미터 저장
        model_info = result["model_info"]
        model_info["subperiod_index"] = sp_idx
        model_info["subperiod_start"] = subperiod["start"]
        model_info["subperiod_end"] = subperiod["end"]
        model_info["commodity_id"] = cid
        model_info["segment"] = seg
        model_info["upstream_col"] = upstream
        model_info["downstream_col"] = downstream
        model_info["effective_lag"] = effective_lag
        model_info["original_lag"] = lag
        model_info["irf_peak_horizon"] = result["irf_data"]["peak_horizon"]
        model_info["irf_peak_magnitude"] = round(result["irf_data"]["peak_magnitude"], 6)

        out_path = (
            output_dir / "subperiod_models"
            / f"{cid}_{seg}_subperiod_{sp_idx}_model.json"
        )
        save_json(model_info, out_path)

        return model_info

    except Exception as e:
        logger.warning(
            'PL-P6-004", "msg": "하위 기간 재추정 실패: %s", '
            '"phase": "6", "context": {"commodity_id": "%s", "segment": "%s", '
            '"subperiod_index": %d}',
            str(e), cid, seg, sp_idx,
        )
        return None


# ──────────────────────────────────────────────
# 구간별 Phase 6 실행
# ──────────────────────────────────────────────
def process_segment(cid, seg, route, df_changes, df_sa, baseline, output_dir):
    """단일 품목·구간에 대해 Bai-Perron + Chow + 하위 기간 분할 + 재추정"""

    upstream = route["upstream"]
    downstream = route["downstream"]
    upstream_pct = f"{upstream}_pct"
    downstream_pct = f"{downstream}_pct"

    # 1. 전이율 산출
    if upstream_pct not in df_changes.columns or downstream_pct not in df_changes.columns:
        logger.warning(
            'SEG_SKIP", "msg": "변화율 컬럼 부재: %s, %s", "phase": "6"',
            upstream_pct, downstream_pct,
        )
        return None

    rate = compute_transmission_rate(df_changes, upstream_pct, downstream_pct)

    if len(rate) < MIN_SUBPERIOD_OBS:
        logger.warning(
            'SEG_SKIP", "msg": "%s %s 전이율 유효 관측치 부족 (%d)", "phase": "6"',
            cid, seg, len(rate),
        )
        return None

    # 2. Bai-Perron
    try:
        bp_indices, best_k, bic_scores = run_bai_perron(rate)
    except Exception as e:
        # PL-P6-001: Bai-Perron 실패 → 단일 기간 fallback
        logger.warning(
            'PL-P6-001", "msg": "Bai-Perron 실패: %s — 단일 기간 유지", '
            '"phase": "6", "context": {"commodity_id": "%s", "segment": "%s"}',
            str(e), cid, seg,
        )
        bp_indices, best_k, bic_scores = [], 0, {}

    bp_dates = []
    for idx in bp_indices:
        if idx < len(rate):
            bp_dates.append(rate.index[idx].strftime("%Y-%m"))

    # 3. Chow Test
    chow_results = {}
    for cp in CHOW_TEST_POINTS:
        cp_date = pd.Timestamp(f"{cp}-01")
        if cp_date < rate.index[0] or cp_date > rate.index[-1]:
            # PL-P6-002
            logger.warning(
                'PL-P6-002", "msg": "Chow 시점 %s 범위 밖", '
                '"phase": "6", "context": {"commodity_id": "%s", "segment": "%s"}',
                cp, cid, seg,
            )
            chow_results[cp] = {
                "f_stat": None, "pvalue": None, "significant": None,
                "note": "분석 범위 밖 (PL-P6-002)",
            }
        else:
            chow_results[cp] = chow_test(rate, cp)

    # 4. 하위 기간 분할
    subperiods = build_subperiods(rate, bp_indices)

    # PL-P6-003: 모든 하위 기간 < 60개 확인
    independent = [sp for sp in subperiods if "merged_with" not in sp]
    if best_k > 0 and all(sp["n_obs"] < MIN_SUBPERIOD_OBS for sp in independent):
        logger.warning(
            'PL-P6-003", "msg": "모든 하위 기간 < %d — 단일 기간 유지", '
            '"phase": "6", "context": {"commodity_id": "%s", "segment": "%s"}',
            MIN_SUBPERIOD_OBS, cid, seg,
        )
        subperiods = [{
            "id": 1,
            "start": rate.index[0].strftime("%Y-%m"),
            "end": rate.index[-1].strftime("%Y-%m"),
            "n_obs": len(rate),
        }]
        independent = subperiods
        bp_dates = []
        best_k = 0

    # 5. 경계 플래그 판정
    is_borderline = (cid, seg) in BORDERLINE_SEGMENTS

    # 6. breakpoints.json 저장
    breakpoints_data = {
        "commodity_id": cid,
        "segment": seg,
        "borderline_cointegration": is_borderline,
        "bai_perron_breakpoints": bp_dates,
        "bai_perron_best_k": best_k,
        "bic_scores": {str(k): round(v, 2) for k, v in bic_scores.items()},
        "chow_test_points": chow_results,
        "subperiods": subperiods,
    }
    save_json(breakpoints_data, output_dir / "breakpoints" / f"{cid}_{seg}_breakpoints.json")

    # 6. Chow CSV 저장
    chow_rows = []
    for cp, res in chow_results.items():
        chow_rows.append({
            "commodity_id": cid, "segment": seg, "break_point": cp,
            "f_stat": res.get("f_stat"), "pvalue": res.get("pvalue"),
            "significant": res.get("significant"), "note": res.get("note", ""),
        })
    pd.DataFrame(chow_rows).to_csv(
        output_dir / "chow_results" / f"{cid}_{seg}_chow.csv",
        index=False, encoding="utf-8-sig",
    )

    # 7. 하위 기간 재추정 (2개 이상 독립 기간이 있을 때만)
    reest_count = 0
    if len(independent) > 1:
        for sp in independent:
            sp_result = reestimate_subperiod(
                df_sa, df_changes, route, sp, output_dir, cid, seg, sp["id"]
            )
            if sp_result is not None:
                reest_count += 1

    return {
        "commodity_id": cid,
        "segment": seg,
        "n_obs": len(rate),
        "n_breakpoints": best_k,
        "bp_dates": bp_dates,
        "n_subperiods": len(independent),
        "borderline": is_borderline,
        "chow_2008_sig": chow_results.get("2008-01", {}).get("significant"),
        "chow_2020_sig": chow_results.get("2020-01", {}).get("significant"),
        "chow_2022_sig": chow_results.get("2022-01", {}).get("significant"),
        "reestimation_count": reest_count,
    }


# ──────────────────────────────────────────────
# 메인 파이프라인
# ──────────────────────────────────────────────
def run_phase6(
    product_config_path=PRODUCT_CONFIG_PATH,
    model_routing_path=MODEL_ROUTING_PATH,
    changes_dir=CHANGES_DIR,
    sa_dir=SA_DIR,
    phase4_dir=PHASE4_DIR,
    output_dir=PHASE6_DIR,
):
    """Phase 6 전체 실행"""
    logger.info(
        'PHASE_START", "msg": "Phase 6 시작 — 구조 변화 탐지 및 기간 분할", "phase": "6"'
    )

    for sub in ["breakpoints", "chow_results", "subperiod_models"]:
        (output_dir / sub).mkdir(parents=True, exist_ok=True)

    config = load_json(product_config_path)
    routing = load_json(model_routing_path)
    summary_rows = []

    for cid, cfg in config.items():
        # 데이터 파일 존재 확인
        if not (changes_dir / f"{cid}_changes.csv").exists():
            logger.warning('DATA_MISSING", "msg": "%s changes 파일 부재"', cid)
            continue
        if not (sa_dir / f"{cid}_sa.csv").exists():
            logger.warning('DATA_MISSING", "msg": "%s sa 파일 부재"', cid)
            continue

        logger.info('ITEM_START", "msg": "%s 시작", "phase": "6"', cid)
        df_changes = load_changes(cid, changes_dir)
        df_sa = load_sa(cid, sa_dir)

        for seg, route in routing[cid].items():
            baseline_path = phase4_dir / "baseline" / f"{cid}_{seg}_baseline.json"
            baseline = load_json(baseline_path) if baseline_path.exists() else None

            result = process_segment(
                cid, seg, route, df_changes, df_sa, baseline, output_dir
            )
            if result is not None:
                summary_rows.append(result)

    # 요약 저장
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_csv(
            output_dir / "phase6_summary.csv", index=False, encoding="utf-8-sig"
        )

    # 콘솔 요약
    print("\n" + "=" * 70)
    print("Phase 6 — 구조 변화 탐지 및 기간 분할 결과")
    print("=" * 70)
    for row in summary_rows:
        bp_str = ", ".join(row["bp_dates"]) if row["bp_dates"] else "없음"
        chow_parts = []
        for yr, key in [("08", "chow_2008_sig"), ("20", "chow_2020_sig"), ("22", "chow_2022_sig")]:
            v = row[key]
            chow_parts.append(f"{yr}{'✔' if v is True else '✗' if v is False else '—'}")
        bl = "⚠" if row.get("borderline") else " "
        print(f" {bl}{row['commodity_id']:12s} {row['segment']:7s} | "
              f"n={row['n_obs']:3d} | BP={row['n_breakpoints']} ({bp_str:30s}) | "
              f"Chow: {' '.join(chow_parts)} | "
              f"기간={row['n_subperiods']} 재추정={row['reestimation_count']}")
    print("=" * 70)

    logger.info('PHASE_DONE", "msg": "Phase 6 완료 — %d개 구간"', len(summary_rows))
    return summary_rows


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    run_phase6()
