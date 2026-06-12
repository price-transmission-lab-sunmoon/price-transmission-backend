"""Phase 7-ML — ml_scores + ml_projections 적재

backend_reply_phase7ml_v2 합의안 기준:
  - percentile: segment 내 rank(pct=True, ascending=False) * 100 — 3종 모두 (높을수록 이상)
  - *_anomaly: NaN → False 강제, 항상 boolean
  - ml_projections: PCA(n_components=2) — x_label='PC1', y_label='PC2' 고정
    (cid, seg, period) × 3 model_name = 3행. 좌표 동일, anomaly_score/is_anomaly만 모델별 상이.

입력:
  data/processed/phase7_ml/predictions/{cid}_{seg}_ml_predictions.csv (20개)
  data/processed/phase7_ml/features/{cid}_{seg}_features.csv (20개)

적재 대상:
  ml_scores       — 품목 × 구간 × 월 단위 모델별 점수 + percentile + 앙상블
  ml_projections  — PCA 2D 좌표 (3행 / 관측치, 모델별)

D-14: ML 학습 단위는 품목×구간. percentile/PCA도 동일 단위로 산출.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.loader.base import append_phase_to_run, validate_period_day

logger = logging.getLogger(__name__)

_PHASE7_ML_ROOT = Path(settings.pipeline_data_root) / "phase7_ml"

# numeric(10,6) max ≈ 9999.999999. 안전 한도.
SCORE_MAX = 9999.0


def _F(val, limit: float = SCORE_MAX) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f) or abs(f) > limit:
        return None
    return f


def _read_predictions() -> pd.DataFrame:
    """phase7_ml/predictions/*.csv 모두 합쳐 단일 DataFrame 반환."""
    pred_dir = _PHASE7_ML_ROOT / "predictions"
    if not pred_dir.exists():
        return pd.DataFrame()
    dfs = []
    for fp in sorted(pred_dir.glob("*_ml_predictions.csv")):
        df = pd.read_csv(fp, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _compute_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """segment 단위 percentile 산출 — 3종 score 모두 동일식 (회신 v2 §1.3).

    핵심: IF/LOF/SVM 모두 'lower score = more anomalous'.
      - IF: score_samples (낮을수록 이상)
      - LOF: negative_outlier_factor_ (더 음수 = 이상)
      - SVM: decision_function (음수 = 이상)
    따라서 3종 모두 ascending=False로 rank → 높은 percentile = 더 이상.
    """
    df = df.copy()
    group = df.groupby(["commodity_id", "segment_id"])
    for src, dst in (
        ("if_score", "if_percentile"),
        ("lof_score", "lof_percentile"),
        ("svm_score", "svm_percentile"),
    ):
        if src in df.columns:
            df[dst] = group[src].rank(pct=True, ascending=False) * 100
        else:
            df[dst] = None
    return df


def _force_bool(val) -> bool:
    """*_anomaly NaN → False 강제 (회신 v2 §2.2)."""
    if val is None:
        return False
    if isinstance(val, float) and math.isnan(val):
        return False
    return bool(val)


async def load_ml_scores(session: AsyncSession, run_id: int) -> int:
    """predictions CSV → ml_scores UPSERT.

    Returns:
        적재된 행 수.
    """
    df = _read_predictions()
    if df.empty:
        logger.warning("phase7_ml/predictions/*.csv 없음 — ml_scores 0행")
        await session.execute(text("DELETE FROM ml_scores"))
        return 0

    df = _compute_percentiles(df)

    # 멱등 적재 — DELETE 후 INSERT (UNIQUE (cid, seg, period) 기준)
    await session.execute(text("DELETE FROM ml_scores"))

    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        period = d.date() if hasattr(d, "date") else d
        validate_period_day(period, "ml_scores")

        rows.append({
            "commodity_id": str(r["commodity_id"]),
            "segment_id": str(r["segment_id"]),
            "period": period,
            "if_score": _F(r.get("if_score")),
            "if_anomaly": _force_bool(r.get("if_anomaly")),
            "if_percentile": _F(r.get("if_percentile"), limit=100.0),
            "lof_score": _F(r.get("lof_score")),
            "lof_anomaly": _force_bool(r.get("lof_anomaly")),
            "lof_percentile": _F(r.get("lof_percentile"), limit=100.0),
            "svm_score": _F(r.get("svm_score")),
            "svm_anomaly": _force_bool(r.get("svm_anomaly")),
            "svm_percentile": _F(r.get("svm_percentile"), limit=100.0),
            "ml_vote": int(r.get("ml_consensus_count") or 0),
            "ml_detected": _force_bool(r.get("ml_detected")),
            "pipeline_run_id": run_id,
        })

    if not rows:
        return 0

    await session.execute(
        text("""
            INSERT INTO ml_scores (
                commodity_id, segment_id, period,
                if_score, if_anomaly, if_percentile,
                lof_score, lof_anomaly, lof_percentile,
                svm_score, svm_anomaly, svm_percentile,
                ml_vote, ml_detected,
                pipeline_run_id
            ) VALUES (
                :commodity_id, :segment_id, :period,
                :if_score, :if_anomaly, :if_percentile,
                :lof_score, :lof_anomaly, :lof_percentile,
                :svm_score, :svm_anomaly, :svm_percentile,
                :ml_vote, :ml_detected,
                :pipeline_run_id
            )
        """),
        rows,
    )
    return len(rows)


# 6 피처 고정 (회신 v2 §2.2 + pipeline_output_spec_v9 §Phase 7-ML)
_PCA_FEATURE_COLS = [
    "transmission_rate",
    "upstream_pct",
    "downstream_pct",
    "ect_or_spread",
    "exchange_rate_pct",
    "intl_price_usd_pct",
]

_MODEL_SCORE_MAP = [
    # (model_name, score_col, anomaly_col)
    ("isolation_forest", "if_score", "if_anomaly"),
    ("lof", "lof_score", "lof_anomaly"),
    ("ocsvm", "svm_score", "svm_anomaly"),
]


def _read_features() -> pd.DataFrame:
    """phase7_ml/features/*.csv 모두 합쳐 단일 DataFrame 반환."""
    feat_dir = _PHASE7_ML_ROOT / "features"
    if not feat_dir.exists():
        return pd.DataFrame()
    dfs = []
    for fp in sorted(feat_dir.glob("*_features.csv")):
        df = pd.read_csv(fp, parse_dates=["date"])
        df = df.rename(columns={"segment": "segment_id"})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _compute_pca_projections(
    features_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
) -> pd.DataFrame:
    """segment 단위 PCA 산출 + predictions 머지.

    각 (cid, seg) 그룹별로 StandardScaler → PCA(n=2). 결측 행은 제외.
    predictions와 (cid, seg, date) 키로 머지하여 모델별 anomaly_score/is_anomaly 부착.

    Returns:
        DataFrame with columns:
            commodity_id, segment_id, date, x_value, y_value,
            (model별 long format은 적재 시점에 풀어냄)
            if_score, lof_score, svm_score, if_anomaly, lof_anomaly, svm_anomaly
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    if features_df.empty:
        return pd.DataFrame()

    out_rows = []
    for (cid, seg), grp in features_df.groupby(["commodity_id", "segment_id"]):
        X = grp[_PCA_FEATURE_COLS].copy()
        valid_mask = X.notna().all(axis=1)
        X_valid = X[valid_mask]
        if len(X_valid) < 2:
            # PCA는 최소 2 관측치 필요
            continue

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_valid)
        pca = PCA(n_components=2, random_state=42)
        XY = pca.fit_transform(X_scaled)

        dates = grp.loc[valid_mask, "date"].reset_index(drop=True)
        for i, d in enumerate(dates):
            out_rows.append({
                "commodity_id": cid,
                "segment_id": seg,
                "date": d,
                "x_value": float(XY[i, 0]),
                "y_value": float(XY[i, 1]),
            })

    if not out_rows:
        return pd.DataFrame()

    proj_df = pd.DataFrame(out_rows)

    if predictions_df.empty:
        # score/anomaly 컬럼은 None으로 채움
        for _, score_col, anom_col in _MODEL_SCORE_MAP:
            proj_df[score_col] = None
            proj_df[anom_col] = False
        return proj_df

    # predictions 머지
    pred_sel = predictions_df[[
        "commodity_id", "segment_id", "date",
        "if_score", "if_anomaly",
        "lof_score", "lof_anomaly",
        "svm_score", "svm_anomaly",
    ]].copy()
    merged = proj_df.merge(
        pred_sel, on=["commodity_id", "segment_id", "date"], how="left",
    )
    return merged


async def load_ml_projections(session: AsyncSession, run_id: int) -> int:
    """features CSV → PCA → ml_projections UPSERT.

    한 관측치당 3행 (model_name = isolation_forest / lof / ocsvm). 좌표 동일.

    Returns:
        적재된 행 수 (관측치 × 3).
    """
    features_df = _read_features()
    if features_df.empty:
        logger.warning("phase7_ml/features/*.csv 없음 — ml_projections 0행")
        await session.execute(text("DELETE FROM ml_projections"))
        return 0

    predictions_df = _read_predictions()
    proj_df = _compute_pca_projections(features_df, predictions_df)

    # 멱등 적재 — DELETE 후 INSERT
    await session.execute(text("DELETE FROM ml_projections"))

    if proj_df.empty:
        return 0

    rows = []
    for _, r in proj_df.iterrows():
        d = r["date"]
        period = d.date() if hasattr(d, "date") else d
        validate_period_day(period, "ml_projections")

        base = {
            "commodity_id": str(r["commodity_id"]),
            "segment_id": str(r["segment_id"]),
            "period": period,
            "projection_method": "pca",
            "x_value": _F(r["x_value"]),
            "y_value": _F(r["y_value"]),
            "x_label": "PC1",
            "y_label": "PC2",
            "pipeline_run_id": run_id,
        }
        for model_name, score_col, anom_col in _MODEL_SCORE_MAP:
            rows.append({
                **base,
                "model_name": model_name,
                "anomaly_score": _F(r.get(score_col)),
                "is_anomaly": _force_bool(r.get(anom_col)),
            })

    await session.execute(
        text("""
            INSERT INTO ml_projections (
                commodity_id, segment_id, period,
                model_name, projection_method,
                x_value, y_value, x_label, y_label,
                anomaly_score, is_anomaly,
                pipeline_run_id
            ) VALUES (
                :commodity_id, :segment_id, :period,
                :model_name, :projection_method,
                :x_value, :y_value, :x_label, :y_label,
                :anomaly_score, :is_anomaly,
                :pipeline_run_id
            )
        """),
        rows,
    )
    return len(rows)


async def load_phase7_ml(session: AsyncSession, run_id: int) -> dict[str, int]:
    """Phase 7-ML 단일 트랜잭션 — ml_scores + ml_projections 적재.

    Returns:
        {"ml_scores": N, "ml_projections": M}
    """
    try:
        scores_count = await load_ml_scores(session, run_id)
        proj_count = await load_ml_projections(session, run_id)
        await session.commit()
    except DBError:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise DBError(
            "DB-TX-001",
            "Phase 7-ML 트랜잭션 롤백 — ml_scores/ml_projections 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    await append_phase_to_run(session, run_id, "7-ml")
    logger.info(
        "Phase 7-ML 완료",
        extra={
            "run_id": run_id,
            "ml_scores": scores_count,
            "ml_projections": proj_count,
        },
    )
    return {"ml_scores": scores_count, "ml_projections": proj_count}
