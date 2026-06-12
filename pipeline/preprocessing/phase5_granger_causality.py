"""
Phase 5 — Granger 인과 방향 확정 (구간 C: PPI ↔ 도매가).

적용 대상: has_wholesale=True 품목(groundnuts, banana, orange).

입력:
  - phase1/changes/{cid}_changes.csv
  - phase3/model_routing.json
  - product_config.json

출력:
  - phase5/granger_results.csv
  - phase5/granger_direction.json
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

SIGNIFICANCE_LEVEL = 0.05
SEGMENT = "C"

BASE_DIR = Path("data/processed")
CHANGES_DIR = BASE_DIR / "phase1" / "changes"
PHASE3_DIR = BASE_DIR / "phase3"
PHASE5_DIR = BASE_DIR / "phase5"
PRODUCT_CONFIG_PATH = BASE_DIR / "product_config.json"
MODEL_ROUTING_PATH = PHASE3_DIR / "model_routing.json"

logging.basicConfig(
    level=logging.INFO,
    format='{"ts": "%(asctime)s", "level": "%(levelname)s", "code": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """파이프라인 에러 기반 클래스."""
    def __init__(self, code: str, message: str, context: dict):
        self.code = code
        self.message = message
        self.context = context
        super().__init__(f"[{code}] {message} | {context}")


def load_configs(product_config_path: Path, model_routing_path: Path):
    with open(product_config_path, "r", encoding="utf-8") as f:
        product_config = json.load(f)
    with open(model_routing_path, "r", encoding="utf-8") as f:
        model_routing = json.load(f)
    return product_config, model_routing


def get_phase5_targets(product_config: dict) -> list[str]:
    """has_wholesale=True 품목 필터링."""
    targets = []
    for cid, cfg in product_config.items():
        if cfg.get("has_wholesale", False):
            targets.append(cid)
        else:
            logger.info(
                'PL-P5-001", "msg": "Phase 5 대상 아님 (3구간 품목)", '
                '"phase": "5", "context": {"commodity_id": "%s", "route_type": "3-segment"}',
                cid,
            )
    return targets


def load_changes_data(cid: str, changes_dir: Path) -> pd.DataFrame:
    filepath = changes_dir / f"{cid}_changes.csv"
    df = pd.read_csv(filepath, parse_dates=["date"], index_col="date")
    df = df.dropna(subset=["ppi_pct", "wholesale_price_pct"])
    return df


def run_granger_test(
    df: pd.DataFrame,
    direction: str,
    max_lag: int,
) -> dict:
    """
    단방향 Granger 인과 검정.

    statsmodels 규약: data[:, 0] = 종속변수, data[:, 1] = 독립변수(원인 후보).
    H0: 독립변수가 종속변수를 Granger-인과하지 않는다.
    각 시차별 ssr_ftest 중 최소 p값 반환.
    """
    if direction == "ppi_to_wholesale":
        # 종속=wholesale, 독립=ppi
        data = df[["wholesale_price_pct", "ppi_pct"]].values
    elif direction == "wholesale_to_ppi":
        # 종속=ppi, 독립=wholesale
        data = df[["ppi_pct", "wholesale_price_pct"]].values
    else:
        raise ValueError(f"Unknown direction: {direction}")

    results = grangercausalitytests(data, maxlag=max_lag, verbose=False)

    best_lag = None
    best_f = None
    best_p = 1.0

    for lag in range(1, max_lag + 1):
        f_stat, p_value, df_denom, df_num = results[lag][0]["ssr_ftest"]
        if p_value < best_p:
            best_p = p_value
            best_f = f_stat
            best_lag = lag

    return {
        "direction": direction,
        "max_lag": max_lag,
        "best_lag": best_lag,
        "f_stat": round(best_f, 4),
        "pvalue": round(best_p, 4),
        "significant": best_p < SIGNIFICANCE_LEVEL,
    }


def determine_confirmed_direction(
    result_ppi_to_ws: dict,
    result_ws_to_ppi: dict,
    cid: str,
) -> str:
    """
    양방향 검정 종합 판정.
    - 한쪽만 유의 → 해당 방향
    - 양방향 유의 → 'bidirectional' (PPI→도매가 기본 방향 유지)
    - 양방향 비유의 → 'none'
    """
    sig_ppi_to_ws = result_ppi_to_ws["significant"]
    sig_ws_to_ppi = result_ws_to_ppi["significant"]

    if sig_ppi_to_ws and sig_ws_to_ppi:
        logger.warning(
            'PL-P5-003", "msg": "양방향 Granger 모두 유의", '
            '"phase": "5", "context": {"commodity_id": "%s"}',
            cid,
        )
        return "bidirectional"

    elif not sig_ppi_to_ws and not sig_ws_to_ppi:
        logger.warning(
            'PL-P5-002", "msg": "양방향 Granger 모두 비유의", '
            '"phase": "5", "context": {"commodity_id": "%s"}',
            cid,
        )
        return "none"

    elif sig_ppi_to_ws:
        return "ppi_to_wholesale"

    else:
        return "wholesale_to_ppi"


def build_granger_direction(
    targets: list[str],
    directions: dict[str, str],
) -> dict:
    """
    후속 Phase 참조용 granger_direction.json 구성.
    구조: {cid: {"segment": "C", "confirmed_direction": ...}}
    """
    result = {}
    for cid in targets:
        result[cid] = {
            "segment": SEGMENT,
            "confirmed_direction": directions[cid],
        }
    return result


def run_phase5(
    product_config_path: Path = PRODUCT_CONFIG_PATH,
    model_routing_path: Path = MODEL_ROUTING_PATH,
    changes_dir: Path = CHANGES_DIR,
    output_dir: Path = PHASE5_DIR,
):
    """Phase 5 전체 실행."""
    logger.info(
        'PHASE_START", "msg": "Phase 5 시작 — Granger 인과 방향 확정", "phase": "5"'
    )

    product_config, model_routing = load_configs(product_config_path, model_routing_path)
    targets = get_phase5_targets(product_config)
    logger.info(
        'PHASE_INFO", "msg": "Phase 5 대상 품목: %s", "phase": "5"',
        targets,
    )

    all_results = []
    confirmed_directions = {}

    for cid in targets:
        logger.info(
            'ITEM_START", "msg": "%s 구간 C Granger 검정 시작", "phase": "5"',
            cid,
        )

        df = load_changes_data(cid, changes_dir)
        n_obs = len(df)

        # 구간 C의 var_lag_aic를 max_lag으로 사용
        max_lag = model_routing[cid][SEGMENT]["var_lag_aic"]

        logger.info(
            'ITEM_INFO", "msg": "%s 관측치=%d, max_lag=%d", "phase": "5"',
            cid, n_obs, max_lag,
        )

        result_ppi_to_ws = run_granger_test(df, "ppi_to_wholesale", max_lag)
        result_ws_to_ppi = run_granger_test(df, "wholesale_to_ppi", max_lag)

        confirmed = determine_confirmed_direction(
            result_ppi_to_ws, result_ws_to_ppi, cid
        )
        confirmed_directions[cid] = confirmed

        for result in [result_ppi_to_ws, result_ws_to_ppi]:
            all_results.append({
                "commodity_id": cid,
                "segment": SEGMENT,
                "direction": result["direction"],
                "max_lag": result["max_lag"],
                "best_lag": result["best_lag"],
                "f_stat": result["f_stat"],
                "pvalue": result["pvalue"],
                "significant": result["significant"],
                "confirmed_direction": confirmed,
            })

        logger.info(
            'ITEM_DONE", "msg": "%s confirmed_direction=%s '
            '(ppi→ws: F=%.4f, p=%.4f, sig=%s | ws→ppi: F=%.4f, p=%.4f, sig=%s)", '
            '"phase": "5"',
            cid, confirmed,
            result_ppi_to_ws["f_stat"], result_ppi_to_ws["pvalue"], result_ppi_to_ws["significant"],
            result_ws_to_ppi["f_stat"], result_ws_to_ppi["pvalue"], result_ws_to_ppi["significant"],
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    results_df = pd.DataFrame(all_results)
    csv_path = output_dir / "granger_results.csv"
    results_df.to_csv(csv_path, index=False)
    logger.info(
        'FILE_SAVED", "msg": "granger_results.csv 저장 완료 (%d행)", "phase": "5"',
        len(results_df),
    )

    granger_direction = build_granger_direction(targets, confirmed_directions)
    json_path = output_dir / "granger_direction.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(granger_direction, f, ensure_ascii=False, indent=2)
    logger.info(
        'FILE_SAVED", "msg": "granger_direction.json 저장 완료 (%d개 품목)", "phase": "5"',
        len(granger_direction),
    )

    print("\n" + "=" * 70)
    print("Phase 5 — Granger 인과 방향 확정 결과")
    print("=" * 70)

    if not all_results:
        print("  결과 없음 (입력 데이터 부재)")
        print("=" * 70)
        return results_df, granger_direction

    for cid in targets:
        rows = [r for r in all_results if r["commodity_id"] == cid]
        if not rows:
            continue
        ppi_row = next((r for r in rows if r["direction"] == "ppi_to_wholesale"), None)
        ws_row = next((r for r in rows if r["direction"] == "wholesale_to_ppi"), None)
        if ppi_row is None or ws_row is None:
            continue
        confirmed = rows[0]["confirmed_direction"]

        print(f"\n[{cid}] 구간 C (PPI ↔ 도매가)")
        print(f"  PPI → 도매가: F={ppi_row['f_stat']:.4f}, p={ppi_row['pvalue']:.4f}"
              f"  {'✔ 유의' if ppi_row['significant'] else '✗ 비유의'}")
        print(f"  도매가 → PPI: F={ws_row['f_stat']:.4f}, p={ws_row['pvalue']:.4f}"
              f"  {'✔ 유의' if ws_row['significant'] else '✗ 비유의'}")

        direction_label = {
            "ppi_to_wholesale": "→ PPI가 도매가를 선행 (PPI → 도매가)",
            "wholesale_to_ppi": "→ 도매가가 PPI를 선행 (도매가 → PPI)",
            "bidirectional": "→ 양방향 인과 (PPI ↔ 도매가) — PPI→도매가 기본 방향 유지",
            "none": "→ 인과 관계 미확인 — Phase 7 패턴 1만 적용",
        }
        print(f"  확정: {direction_label.get(confirmed, confirmed)}")

    print("\n" + "=" * 70)

    logger.info(
        'PHASE_DONE", "msg": "Phase 5 완료 — %d개 품목 검정 완료", "phase": "5"',
        len(targets),
    )

    return results_df, granger_direction


if __name__ == "__main__":
    run_phase5()
