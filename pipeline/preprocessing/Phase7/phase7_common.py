"""
Phase 7 공통 기반 모듈 (phase7_common.py)
=========================================
역할:
  Phase 7 이상 패턴 탐지에서 패턴 1/2/3이 공통으로 사용하는
  데이터 로딩, 전이율 산출, 하위 기간 판별 함수를 제공한다.

입력 파일:
  - data/processed/product_config.json
  - data/processed/phase3/model_routing.json
  - data/processed/phase5/granger_direction.json
  - data/processed/phase1/changes/{cid}_changes.csv
  - data/processed/phase1/seasonal_adjusted/{cid}_sa.csv
  - data/processed/phase4/baseline/{cid}_{seg}_baseline.json
  - data/processed/phase4/ect/{cid}_{seg}_ect.csv
  - data/processed/phase4/irf/{cid}_{seg}_irf.csv
  - data/processed/phase6/breakpoints/{cid}_{seg}_breakpoints.json
  - data/processed/phase6/subperiod_models/{cid}_{seg}_subperiod_{n}_model.json

출력 파일:
  없음 (라이브러리 모듈)

파라미터 (settings.py 기준):
  ROLLING_WINDOW = 48
  ROLLING_WINDOW_ROBUSTNESS = [36, 48, 60]
  ZSCORE_WARNING = 2.0
  ZSCORE_ALERT = 2.5
  IQR_MULTIPLIER = 1.5
  STABILITY_THRESHOLD = 0.03
  PATTERN3_N_VALUES = [2, 3, 6]
  TRANSMISSION_RATE_MIN_UPSTREAM = 0.5  (상류 변화율 절대값 최소 임계, %)
"""

import json
import os
import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# 파라미터 (settings.py 기준값 + Phase 7 추가 파라미터)
# ---------------------------------------------------------------------------
ROLLING_WINDOW = 48
ROLLING_WINDOW_ROBUSTNESS = [36, 48, 60]
ZSCORE_WARNING = 2.0
ZSCORE_ALERT = 2.5
IQR_MULTIPLIER = 1.5
STABILITY_THRESHOLD = 0.03
PATTERN3_N_VALUES = [2, 3, 6]

# 전이율 산출 시 상류 변화율 절대값 최소 임계 (%)
# 이 값 미만이면 전이율을 NaN 처리 (분모 폭발 방지)
TRANSMISSION_RATE_MIN_UPSTREAM = 0.5

# 방향 역전 판정 시 최소 변동 크기 (%)
# 상류/하류 둘 다 이 값 이상이어야 방향 역전으로 판정
# 가격 전달 시차가 존재하므로 동시점 미세 변동은 노이즈로 간주
DIRECTION_REVERSAL_MIN_MAGNITUDE = 1.0

# 패턴 적용 범위
PATTERN1_SEGMENTS = ["A", "B", "C", "D", "D_prime"]  # 전 구간
PATTERN2_SEGMENTS = ["A", "B"]                         # A, B만
PATTERN3_SEGMENTS = ["B"]                              # B만
ASYMMETRY_SEGMENTS = ["A", "B"]                        # A, B만

# 동월 복수 패턴 심각도 우선순위 (높을수록 심각)
PATTERN_SEVERITY = {"pattern2": 3, "pattern1": 2, "pattern3": 1}


# ---------------------------------------------------------------------------
# 데이터 경로 설정
# ---------------------------------------------------------------------------
class DataPaths:
    """프로젝트 데이터 경로를 관리한다."""

    def __init__(self, base_dir):
        self.base = Path(base_dir)
        self.product_config = self.base / "product_config.json"
        self.model_routing = self.base / "phase3" / "model_routing.json"
        self.granger_direction = self.base / "phase5" / "granger_direction.json"
        self.changes_dir = self.base / "phase1" / "changes"
        self.sa_dir = self.base / "phase1" / "seasonal_adjusted"
        self.baseline_dir = self.base / "phase4" / "baseline"
        self.ect_dir = self.base / "phase4" / "ect"
        self.irf_dir = self.base / "phase4" / "irf"
        self.breakpoints_dir = self.base / "phase6" / "breakpoints"
        self.subperiod_models_dir = self.base / "phase6" / "subperiod_models"


# ---------------------------------------------------------------------------
# 설정 파일 로딩
# ---------------------------------------------------------------------------
def load_product_config(paths):
    """product_config.json을 로드한다."""
    with open(paths.product_config, "r", encoding="utf-8") as f:
        return json.load(f)


def load_model_routing(paths):
    """model_routing.json을 로드한다."""
    with open(paths.model_routing, "r", encoding="utf-8") as f:
        return json.load(f)


def load_granger_direction(paths):
    """granger_direction.json을 로드한다."""
    with open(paths.granger_direction, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 품목별 데이터 로딩
# ---------------------------------------------------------------------------
def load_changes(paths, cid):
    """
    Phase 1 변화율 CSV를 로드한다.

    반환: DatetimeIndex(MS)를 인덱스로 갖는 DataFrame.
    """
    filepath = paths.changes_dir / f"{cid}_changes.csv"
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.index.freq = "MS"
    return df


def load_seasonal_adjusted(paths, cid):
    """
    Phase 1 계절 조정 수준 데이터 CSV를 로드한다.

    반환: DatetimeIndex(MS)를 인덱스로 갖는 DataFrame.
    """
    filepath = paths.sa_dir / f"{cid}_sa.csv"
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.index.freq = "MS"
    return df


def load_baseline(paths, cid, seg):
    """
    Phase 4 기준선 JSON을 로드한다.

    반환: dict (normal_transmission_lag, transmission_elasticity, warmup_end 등)
    """
    filepath = paths.baseline_dir / f"{cid}_{seg}_baseline.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ect(paths, cid, seg):
    """
    Phase 4 ECT/로그 스프레드 CSV를 로드한다.

    반환: DatetimeIndex(MS)를 인덱스로 갖는 DataFrame (ect, ect_type 컬럼).
    """
    filepath = paths.ect_dir / f"{cid}_{seg}_ect.csv"
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.index.freq = "MS"
    return df


def load_irf(paths, cid, seg):
    """
    Phase 4 IRF 시계열 CSV를 로드한다.

    반환: DataFrame (horizon, irf_downstream 등)
    """
    filepath = paths.irf_dir / f"{cid}_{seg}_irf.csv"
    return pd.read_csv(filepath, encoding="utf-8-sig")


def load_breakpoints(paths, cid, seg):
    """
    Phase 6 구조 변화 JSON을 로드한다.

    반환: dict (bai_perron_breakpoints, subperiods 등)
    """
    filepath = paths.breakpoints_dir / f"{cid}_{seg}_breakpoints.json"
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_subperiod_model(paths, cid, seg, subperiod_id):
    """
    Phase 6 하위 기간 재추정 모형 JSON을 로드한다.

    반환: dict 또는 None (파일 미존재 시)
    """
    filepath = (
        paths.subperiod_models_dir
        / f"{cid}_{seg}_subperiod_{subperiod_id}_model.json"
    )
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 하위 기간 판별
# ---------------------------------------------------------------------------
class SubperiodResolver:
    """
    특정 날짜가 어느 하위 기간(subperiod)에 속하는지 판별하고,
    해당 기간의 기준선(IRF 피크 시차, 탄력성)을 반환한다.

    구조 변화가 없는 구간에서는 전체 기간 baseline을 그대로 사용한다.
    """

    def __init__(self, paths, cid, seg):
        self.cid = cid
        self.seg = seg
        self.paths = paths

        # 전체 기간 기준선 (항상 존재)
        self.full_baseline = load_baseline(paths, cid, seg)

        # breakpoints 로드
        bp_data = load_breakpoints(paths, cid, seg)
        self.has_structural_break = len(bp_data["bai_perron_breakpoints"]) > 0
        self.subperiods = bp_data.get("subperiods", [])

        # 하위 기간별 모형 로드 (구조 변화 있는 구간만)
        self.subperiod_models = {}
        if self.has_structural_break:
            for sp in self.subperiods:
                model = load_subperiod_model(paths, cid, seg, sp["id"])
                if model is not None:
                    self.subperiod_models[sp["id"]] = model

    def get_normal_lag(self, date):
        """
        주어진 날짜의 정상 전달 시차를 반환한다.

        구조 변화가 있는 구간: 해당 날짜가 속한 subperiod의 irf_peak_horizon 사용.
        구조 변화가 없는 구간: 전체 기간 baseline의 normal_transmission_lag 사용.
        """
        if not self.has_structural_break:
            return self.full_baseline["normal_transmission_lag"]

        sp_id = self._find_subperiod_id(date)
        if sp_id is not None and sp_id in self.subperiod_models:
            return self.subperiod_models[sp_id]["irf_peak_horizon"]

        # subperiod_model이 없으면 전체 기간 기준선 폴백
        return self.full_baseline["normal_transmission_lag"]

    def get_elasticity(self, date):
        """
        주어진 날짜의 전이탄력성을 반환한다.
        """
        if not self.has_structural_break:
            return self.full_baseline["transmission_elasticity"]

        sp_id = self._find_subperiod_id(date)
        if sp_id is not None and sp_id in self.subperiod_models:
            return self.subperiod_models[sp_id]["irf_peak_magnitude"]

        return self.full_baseline["transmission_elasticity"]

    def get_subperiod_id(self, date):
        """
        주어진 날짜가 속한 subperiod ID를 반환한다.
        구조 변화가 없는 구간이면 None을 반환한다.
        """
        if not self.has_structural_break:
            return None
        return self._find_subperiod_id(date)

    def _find_subperiod_id(self, date):
        """날짜를 subperiods 목록과 대조하여 해당 ID를 반환한다."""
        if isinstance(date, str):
            date = pd.Timestamp(date)
        for sp in self.subperiods:
            sp_start = pd.Timestamp(sp["start"] + "-01")
            sp_end = pd.Timestamp(sp["end"] + "-01")
            if sp_start <= date <= sp_end:
                return sp["id"]
        return None


# ---------------------------------------------------------------------------
# 전이율 산출
# ---------------------------------------------------------------------------
def compute_transmission_rate(upstream_pct, downstream_pct,
                              min_upstream=TRANSMISSION_RATE_MIN_UPSTREAM):
    """
    월별 전이율을 산출한다.

    전이율 = downstream_pct / upstream_pct.
    상류 변화율 절대값이 min_upstream(%) 미만이면 NaN 처리한다.

    Args:
        upstream_pct: 상류 가격 변화율 Series (%)
        downstream_pct: 하류 가격 변화율 Series (%)
        min_upstream: 상류 변화율 절대값 최소 임계 (%, 기본 0.5)

    Returns:
        전이율 Series (NaN 포함 가능)
    """
    tr = pd.Series(np.nan, index=upstream_pct.index, dtype=float)
    valid_mask = (
        upstream_pct.notna()
        & downstream_pct.notna()
        & (upstream_pct.abs() >= min_upstream)
    )
    tr[valid_mask] = downstream_pct[valid_mask] / upstream_pct[valid_mask]
    return tr


# ---------------------------------------------------------------------------
# 구간별 변화율 컬럼명 조회
# ---------------------------------------------------------------------------
def get_pct_columns(config, cid, seg):
    """
    product_config에서 해당 구간의 상류/하류 원본 컬럼명과
    changes CSV에서의 _pct 컬럼명을 반환한다.

    Returns:
        (upstream_raw, downstream_raw, upstream_pct, downstream_pct)
        예: ('intl_price_krw', 'import_price_usd',
             'intl_price_krw_pct', 'import_price_usd_pct')
    """
    pair = config[cid]["segment_pairs"][seg]
    upstream_raw = pair[0]
    downstream_raw = pair[1]
    upstream_pct = upstream_raw + "_pct"
    downstream_pct = downstream_raw + "_pct"
    return upstream_raw, downstream_raw, upstream_pct, downstream_pct


# ---------------------------------------------------------------------------
# warmup 종료 시점
# ---------------------------------------------------------------------------
def get_warmup_end(baseline):
    """
    baseline JSON의 warmup_end를 Timestamp로 반환한다.

    warmup_end 이전 기간은 롤링 윈도우 기준 분포 축적 기간으로,
    패턴 2의 Z-score/IQR 탐지를 수행하지 않는다.
    """
    return pd.Timestamp(baseline["warmup_end"] + "-01")


# ---------------------------------------------------------------------------
# 구간 반복 유틸리티
# ---------------------------------------------------------------------------
def iter_segments(config, segment_filter=None):
    """
    품목x구간 조합을 순회하는 제너레이터.

    Args:
        config: product_config dict
        segment_filter: 허용할 구간 목록 (예: ['A','B']). None이면 전체.

    Yields:
        (commodity_id, segment_id)
    """
    for cid, cfg in config.items():
        for seg in cfg["segments"]:
            if segment_filter is not None and seg not in segment_filter:
                continue
            yield cid, seg


def get_segment_count(config, segment_filter=None):
    """segment_filter에 해당하는 품목x구간 조합 수를 반환한다."""
    return sum(1 for _ in iter_segments(config, segment_filter))


# ---------------------------------------------------------------------------
# 출력 디렉토리 생성
# ---------------------------------------------------------------------------
def ensure_output_dirs(output_base):
    """Phase 7 출력 디렉토리 구조를 생성한다."""
    dirs = [
        "pattern1",
        "pattern2",
        "pattern3",
        "robustness",
        "stat_timeseries",
    ]
    output_base = Path(output_base)
    for d in dirs:
        (output_base / d).mkdir(parents=True, exist_ok=True)
    return output_base


# ---------------------------------------------------------------------------
# 로깅 유틸리티
# ---------------------------------------------------------------------------
def log(msg):
    """간단한 콘솔 로그 출력."""
    print(f"[Phase7] {msg}")