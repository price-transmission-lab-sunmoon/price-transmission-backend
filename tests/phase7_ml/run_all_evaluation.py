"""5축 ML 신뢰성 평가 통합 실행 — 타임스탬프 디렉토리에 축별 CSV + 메타 JSON 저장.

입력: Phase 7-ML 출력 + Phase 7 stat 출력 + product_config
출력: tests/phase7_ml/results/run_{timestamp}/ 아래 축별 CSV + run_meta.json + latest/ 복사본
"""

import sys
import os
import json
import shutil
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_common import log_eval
from test_axis1_esr import run_axis1
from test_axis2_separation import run_axis2
from test_axis3_auc import run_axis3
from test_axis4_sensitivity import run_axis4
from test_axis5_consensus import run_axis5


def collect_ml_parameters(ml_dir):
    """Phase 7-ML run_log에서 파라미터를 읽어온다. 로그 없으면 기본값 반환."""
    ml_dir = Path(ml_dir)
    models_dir = ml_dir / "models"

    log_files = sorted(models_dir.glob("run_log_*.json"), reverse=True) if models_dir.exists() else []

    if log_files:
        with open(log_files[0], "r", encoding="utf-8") as f:
            run_log = json.load(f)
        return run_log.get("parameters", {}), log_files[0].name
    else:
        return {
            "isolation_forest": {"n_estimators": 100, "contamination": 0.10, "random_state": 42},
            "lof": {"n_neighbors": 10, "contamination": 0.10, "novelty": False},
            "ocsvm": {"kernel": "rbf", "nu": 0.10, "gamma": "scale"},
            "preprocessing": {
                "scaler": "StandardScaler",
                "consensus_threshold": 2,
            },
        }, None


def collect_feature_list(ml_dir):
    ml_dir = Path(ml_dir)
    features_dir = ml_dir / "features"
    if not features_dir.exists():
        return []

    feature_files = list(features_dir.glob("*_features.csv"))
    if not feature_files:
        return []

    df = pd.read_csv(feature_files[0], nrows=1, encoding="utf-8-sig")
    skip_cols = {"date", "commodity_id", "segment"}
    return [c for c in df.columns if c not in skip_cols]


def run_all(data_dir, ml_dir, phase7_dir, results_base, memo=""):
    """5축 평가를 순차 실행하고 타임스탬프 디렉토리에 결과를 저장한다."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{timestamp}"
    output = Path(results_base) / run_id
    output.mkdir(parents=True, exist_ok=True)

    log_eval("=" * 60)
    log_eval(f"ML 신뢰성 평가 시작 (5축) — {run_id}")
    if memo:
        log_eval(f"메모: {memo}")
    log_eval("=" * 60)
    print()

    esr_results, esr_weighted = run_axis1(data_dir, ml_dir)
    esr_df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "shock_details"}
        for r in esr_results
    ])
    esr_df.to_csv(output / "axis1_esr.csv", index=False, encoding="utf-8-sig")
    print()

    sep_results = run_axis2(data_dir, ml_dir)
    sep_df = pd.DataFrame(sep_results)
    sep_df.to_csv(output / "axis2_separation.csv", index=False, encoding="utf-8-sig")
    print()

    auc_results = run_axis3(data_dir, ml_dir)
    # roc_curves는 별도 JSON에 저장, CSV에는 스칼라만
    roc_curves_all = {}
    auc_results_clean = []
    for r in auc_results:
        rc = r.pop("roc_curves", {})
        cid, seg = r["commodity_id"], r["segment"]
        roc_curves_all[f"{cid}_{seg}"] = rc
        auc_results_clean.append(r)
    auc_df = pd.DataFrame(auc_results_clean)
    auc_df.to_csv(output / "axis3_auc.csv", index=False, encoding="utf-8-sig")
    with open(output / "axis3_roc_curves.json", "w", encoding="utf-8") as f:
        json.dump(roc_curves_all, f)
    print()

    sens_results = run_axis4(data_dir, phase7_dir)
    sens_summary = []
    for r in sens_results:
        contam_srs = [
            c["stability_ratio"]
            for c in r["contamination_sensitivity"]
            if c["contamination"] != 0.10
            and c["stability_ratio"] is not None
            and not np.isnan(c["stability_ratio"])
        ]
        avg_contam = np.mean(contam_srs) if contam_srs else np.nan

        k_srs = [
            k["stability_ratio"]
            for k in r["lof_k_sensitivity"]
            if k["lof_k"] != 10
            and k["stability_ratio"] is not None
            and not np.isnan(k["stability_ratio"])
        ]
        avg_k = np.mean(k_srs) if k_srs else np.nan

        sens_summary.append({
            "commodity_id": r["commodity_id"],
            "segment": r["segment"],
            "n_base": r["n_base"],
            "avg_contam_sr": round(avg_contam, 4) if not np.isnan(avg_contam) else np.nan,
            "avg_k_sr": round(avg_k, 4) if not np.isnan(avg_k) else np.nan,
        })

    sens_df = pd.DataFrame(sens_summary)
    sens_df.to_csv(output / "axis4_sensitivity.csv", index=False, encoding="utf-8-sig")
    print()

    cons_results = run_axis5(data_dir, ml_dir)
    cons_df = pd.DataFrame(cons_results)
    cons_df.to_csv(output / "axis5_consensus.csv", index=False, encoding="utf-8-sig")
    print()

    total_shocks = sum(r["n_shocks"] for r in esr_results)
    if total_shocks > 0:
        weighted_esr = sum(
            r["esr_ml"] * r["n_shocks"]
            for r in esr_results if not np.isnan(r.get("esr_ml", np.nan))
        ) / total_shocks
    else:
        weighted_esr = np.nan

    avg_sr_if = sep_df["sr_if"].mean()
    avg_sr_lof = sep_df["sr_lof"].mean()
    avg_sr_svm = sep_df["sr_svm"].mean()
    avg_auc_ens = auc_df["auc_ensemble"].mean()
    avg_contam_sr = sens_df["avg_contam_sr"].mean()
    avg_k_sr = sens_df["avg_k_sr"].mean()
    avg_cta = cons_df["cta"].mean()
    avg_asc = cons_df["asc"].dropna().mean()

    avg_p_stat = cons_df["p_stat"].dropna().mean() if "p_stat" in cons_df.columns else np.nan
    avg_p_ml = cons_df["p_ml"].dropna().mean() if "p_ml" in cons_df.columns else np.nan

    valid_cons = cons_df[cons_df["hypothesis_holds"].notna()]
    n_holds = int(valid_cons["hypothesis_holds"].sum()) if len(valid_cons) > 0 else 0
    n_valid = len(valid_cons)

    summary = {
        "weighted_esr": round(float(weighted_esr), 4) if not np.isnan(weighted_esr) else None,
        "avg_sr_if": round(float(avg_sr_if), 3),
        "avg_sr_lof": round(float(avg_sr_lof), 3),
        "avg_sr_svm": round(float(avg_sr_svm), 3),
        "avg_auc_ensemble": round(float(avg_auc_ens), 4),
        "avg_contam_sr": round(float(avg_contam_sr), 4),
        "avg_k_sr": round(float(avg_k_sr), 4),
        "avg_cta": round(float(avg_cta), 4),
        "avg_asc": round(float(avg_asc), 4) if not np.isnan(avg_asc) else None,
        "avg_p_stat": round(float(avg_p_stat), 4) if not np.isnan(avg_p_stat) else None,
        "avg_p_ml": round(float(avg_p_ml), 4) if not np.isnan(avg_p_ml) else None,
        "hypothesis_holds": f"{n_holds}/{n_valid}",
    }

    ml_params, log_source = collect_ml_parameters(ml_dir)
    feature_list = collect_feature_list(ml_dir)

    run_meta = {
        "run_id": run_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "memo": memo if memo else "메모 없음",
        "parameters": ml_params,
        "features": {
            "n_features": len(feature_list),
            "feature_list": feature_list,
        },
        "ml_run_log_source": log_source,
        "summary": summary,
        "files": [
            "axis1_esr.csv",
            "axis2_separation.csv",
            "axis3_auc.csv",
            "axis3_roc_curves.json",
            "axis4_sensitivity.csv",
            "axis5_consensus.csv",
        ],
    }

    meta_path = output / "run_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2, ensure_ascii=False)

    latest_dir = Path(results_base) / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(output, latest_dir)

    log_eval("=" * 60)
    log_eval("종합 리포트")
    log_eval("=" * 60)

    print()
    print("=== 축 1: 외부 충격 회수율 (ESR) ===")
    print(f"전체 가중 ESR_ml: {weighted_esr:.4f}")
    print(esr_df[["commodity_id", "segment", "n_shocks", "esr_ml"]].to_string(index=False))

    print()
    print("=== 축 2: 이상 점수 분리도 ===")
    print(f"평균 SR: IF={avg_sr_if:.3f}, LOF={avg_sr_lof:.3f}, SVM={avg_sr_svm:.3f}")
    print(sep_df.to_string(index=False))

    print()
    print("=== 축 3: 통계-ML 일관성 AUC ===")
    print(f"평균 AUC: IF={auc_df['auc_if'].mean():.4f}, LOF={auc_df['auc_lof'].mean():.4f}, SVM={auc_df['auc_svm'].mean():.4f}, ensemble={avg_auc_ens:.4f}")
    print(auc_df.to_string(index=False))

    print()
    print("=== 축 4: 파라미터 민감도 ===")
    print(f"평균 contamination SR: {avg_contam_sr:.4f}")
    print(f"평균 LOF k SR: {avg_k_sr:.4f}")
    print(sens_df.to_string(index=False))

    print()
    print("=== 축 5: 합의 기반 지표 ===")
    print(f"CTA 평균: {avg_cta:.4f}")
    print(f"ASC 평균: {avg_asc:.4f}")
    if not np.isnan(avg_p_stat):
        print(f"P_stat 평균: {avg_p_stat:.4f}")
        print(f"P_ml 평균: {avg_p_ml:.4f}")
    print(f"핵심 가설 (ASC > max(P_stat, P_ml)) 성립: {n_holds}/{n_valid} 구간")
    print(cons_df[["commodity_id", "segment", "cta", "asc", "p_stat", "p_ml", "esr_stat", "esr_ml", "hypothesis_holds"]].to_string(index=False))

    print()
    log_eval(f"결과 저장: {output}")
    log_eval(f"메타 저장: {meta_path}")
    log_eval(f"latest 갱신: {latest_dir}")

    return run_id, output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ML 5축 신뢰성 평가")
    parser.add_argument("--memo", type=str, default="", help="이번 실행에 대한 메모 (예: '피처 추가 실험 v2')")
    args = parser.parse_args()

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
    ML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7_ml")
    PHASE7_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "phase7")
    RESULTS_BASE = os.path.join(os.path.dirname(__file__), "results")

    run_id, output_path = run_all(DATA_DIR, ML_DIR, PHASE7_DIR, RESULTS_BASE, memo=args.memo)