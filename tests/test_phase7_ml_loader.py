"""Phase 7-ML loader 단위 테스트 — backend_reply_phase7ml_v2 합의안 검증.

검증 대상:
  - percentile 산출 — segment 단위 (1 - rank) * 100, 3종 모두 "높을수록 이상"
  - *_anomaly NaN → False 강제
  - 점수 NULL → percentile NULL
"""
from __future__ import annotations

import math
import os

import pandas as pd
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.db.loader.phase7_ml import (
    _compute_pca_projections,
    _compute_percentiles,
    _force_bool,
    _F,
    _MODEL_SCORE_MAP,
    _PCA_FEATURE_COLS,
)


# ── _force_bool ───────────────────────────────────────────────────────────────

def test_force_bool_true():
    assert _force_bool(True) is True


def test_force_bool_false():
    assert _force_bool(False) is False


def test_force_bool_none():
    """None → False (회신 v2 §2.2)."""
    assert _force_bool(None) is False


def test_force_bool_nan():
    """NaN → False — *_anomaly null 금지."""
    assert _force_bool(float("nan")) is False


def test_force_bool_truthy():
    assert _force_bool(1) is True
    assert _force_bool("x") is True


def test_force_bool_falsy():
    assert _force_bool(0) is False
    assert _force_bool("") is False


# ── _F (numeric overflow guard) ────────────────────────────────────────────────

def test_F_normal():
    assert _F(0.42) == 0.42


def test_F_nan():
    assert _F(float("nan")) is None


def test_F_inf():
    assert _F(float("inf")) is None


def test_F_overflow():
    # SCORE_MAX = 9999.0
    assert _F(10000.0) is None


def test_F_percentile_limit():
    # percentile은 0~100 범위로 별도 limit
    assert _F(99.5, limit=100.0) == 99.5
    assert _F(150.0, limit=100.0) is None


# ── _compute_percentiles — 핵심 (회신 v2 §1.3) ────────────────────────────────

def _sample_predictions() -> pd.DataFrame:
    """3개 segment 동일, 5건 관측치."""
    return pd.DataFrame({
        "commodity_id": ["wheat"] * 5,
        "segment_id": ["A"] * 5,
        "date": pd.date_range("2024-01-01", periods=5, freq="MS"),
        # IF score: 낮을수록 이상 → 최저값 -1.5가 100% percentile
        "if_score": [-1.5, -1.0, -0.5, 0.0, 0.5],
        # LOF score: 낮을수록 이상 (negative_outlier_factor)
        "lof_score": [-3.0, -2.0, -1.5, -1.1, -1.0],
        # SVM decision_function: 음수=이상 → 가장 음수가 최상위 이상
        "svm_score": [-0.4, -0.2, 0.0, 0.1, 0.2],
    })


def test_compute_percentiles_if_direction():
    """IF score 가장 낮은 행이 percentile 100 — '높을수록 이상' 통일."""
    df = _compute_percentiles(_sample_predictions())
    assert df.loc[0, "if_percentile"] == pytest.approx(100.0)
    assert df.loc[4, "if_percentile"] == pytest.approx(20.0)


def test_compute_percentiles_lof_direction():
    """LOF score도 낮을수록 이상 (negative_outlier_factor)."""
    df = _compute_percentiles(_sample_predictions())
    assert df.loc[0, "lof_percentile"] == pytest.approx(100.0)
    assert df.loc[4, "lof_percentile"] == pytest.approx(20.0)


def test_compute_percentiles_svm_direction():
    """SVM decision_function 음수=이상 → 가장 음수가 최상위 percentile."""
    df = _compute_percentiles(_sample_predictions())
    assert df.loc[0, "svm_percentile"] == pytest.approx(100.0)
    assert df.loc[4, "svm_percentile"] == pytest.approx(20.0)


def test_compute_percentiles_range_0_100():
    """모든 percentile은 0~100 범위."""
    df = _compute_percentiles(_sample_predictions())
    for col in ("if_percentile", "lof_percentile", "svm_percentile"):
        vals = df[col].dropna().tolist()
        assert all(0 <= v <= 100 for v in vals), f"{col} 범위 이탈: {vals}"


def test_compute_percentiles_segment_independent():
    """segment 단위로 독립 산출 — wheat·A와 wheat·B의 score 분포가 섞이지 않아야 함."""
    df = pd.DataFrame({
        "commodity_id": ["wheat"] * 3 + ["wheat"] * 3,
        "segment_id": ["A"] * 3 + ["B"] * 3,
        "date": list(pd.date_range("2024-01-01", periods=3, freq="MS")) * 2,
        "if_score": [-1.0, -0.5, 0.0, 100.0, 200.0, 300.0],  # B segment는 큰 값
        "lof_score": [-1.0, -0.5, 0.0, 100.0, 200.0, 300.0],
        "svm_score": [-1.0, -0.5, 0.0, 100.0, 200.0, 300.0],
    })
    out = _compute_percentiles(df)
    # A segment 내부에서만 ranking
    assert out.loc[0, "if_percentile"] == pytest.approx(100.0)  # A 최저
    # B segment 내부에서만 ranking
    assert out.loc[3, "if_percentile"] == pytest.approx(100.0)  # B 최저(=100 in B)


def test_compute_percentiles_null_score_null_percentile():
    """점수 자체가 NULL인 행은 percentile도 NULL."""
    df = pd.DataFrame({
        "commodity_id": ["wheat", "wheat", "wheat"],
        "segment_id": ["A", "A", "A"],
        "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
        "if_score": [-1.0, float("nan"), 0.5],
        "lof_score": [float("nan"), float("nan"), float("nan")],
        "svm_score": [-1.0, -0.5, 0.0],
    })
    out = _compute_percentiles(df)
    assert math.isnan(out.loc[1, "if_percentile"])
    assert out.loc[0, "if_percentile"] == pytest.approx(100.0)
    # LOF 전부 NaN → percentile 전부 NaN
    assert out["lof_percentile"].isna().all()


def test_compute_percentiles_single_observation():
    """segment 내 관측치 1건 — rank(pct=True)=1.0 → percentile=100.0."""
    df = pd.DataFrame({
        "commodity_id": ["wheat"],
        "segment_id": ["A"],
        "date": [pd.Timestamp("2024-01-01")],
        "if_score": [-1.0],
        "lof_score": [-1.0],
        "svm_score": [-1.0],
    })
    out = _compute_percentiles(df)
    assert out.loc[0, "if_percentile"] == pytest.approx(100.0)
    assert out.loc[0, "lof_percentile"] == pytest.approx(100.0)
    assert out.loc[0, "svm_percentile"] == pytest.approx(100.0)


def test_compute_percentiles_missing_score_column():
    """if_score 컬럼이 아예 없으면 percentile 컬럼은 None."""
    df = pd.DataFrame({
        "commodity_id": ["wheat"] * 3,
        "segment_id": ["A"] * 3,
        "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
        "lof_score": [-1.0, -0.5, 0.0],
        "svm_score": [-1.0, -0.5, 0.0],
    })
    out = _compute_percentiles(df)
    assert (out["if_percentile"].isna()).all()
    # lof, svm은 정상 산출
    assert out.loc[0, "lof_percentile"] == pytest.approx(100.0)


# ── _compute_pca_projections — 회신 v2 §2.2 ───────────────────────────────────

def _sample_features(n: int = 10) -> pd.DataFrame:
    """6 피처 sample. PCA 산출 가능한 최소 분포."""
    import numpy as np
    rng = np.random.default_rng(seed=42)
    return pd.DataFrame({
        "commodity_id": ["wheat"] * n,
        "segment_id": ["A"] * n,
        "date": pd.date_range("2024-01-01", periods=n, freq="MS"),
        "transmission_rate": rng.normal(1.0, 0.5, n),
        "upstream_pct": rng.normal(0.0, 1.0, n),
        "downstream_pct": rng.normal(0.0, 1.0, n),
        "ect_or_spread": rng.normal(0.0, 0.5, n),
        "exchange_rate_pct": rng.normal(0.0, 0.8, n),
        "intl_price_usd_pct": rng.normal(0.0, 1.2, n),
    })


def _sample_predictions_for_features(features_df: pd.DataFrame) -> pd.DataFrame:
    n = len(features_df)
    return pd.DataFrame({
        "commodity_id": features_df["commodity_id"].values,
        "segment_id": features_df["segment_id"].values,
        "date": features_df["date"].values,
        "if_score": [-0.1 * (i + 1) for i in range(n)],
        "if_anomaly": [i == 0 for i in range(n)],
        "lof_score": [-0.2 * (i + 1) for i in range(n)],
        "lof_anomaly": [i == 0 for i in range(n)],
        "svm_score": [-0.05 * (i + 1) for i in range(n)],
        "svm_anomaly": [i == 0 for i in range(n)],
    })


def test_pca_feature_columns_fixed():
    """피처 6종 + 순서 고정 (회신 v2 §2.2)."""
    assert _PCA_FEATURE_COLS == [
        "transmission_rate", "upstream_pct", "downstream_pct",
        "ect_or_spread", "exchange_rate_pct", "intl_price_usd_pct",
    ]


def test_pca_model_score_map():
    """3종 모델 매핑 — model_name과 score/anomaly 컬럼 짝."""
    names = [m[0] for m in _MODEL_SCORE_MAP]
    assert names == ["isolation_forest", "lof", "ocsvm"]


def test_pca_projections_output_shape():
    """PCA 결과 컬럼 및 값 범위."""
    feat = _sample_features(8)
    preds = _sample_predictions_for_features(feat)
    out = _compute_pca_projections(feat, preds)

    assert len(out) == 8
    for col in ("x_value", "y_value", "if_score", "lof_score", "svm_score"):
        assert col in out.columns
    # PCA 좌표는 finite
    assert out["x_value"].notna().all()
    assert out["y_value"].notna().all()


def test_pca_projections_no_predictions():
    """predictions 없어도 좌표는 산출. score/anomaly는 비어있음."""
    feat = _sample_features(5)
    out = _compute_pca_projections(feat, pd.DataFrame())
    assert len(out) == 5
    assert out["x_value"].notna().all()
    # score는 None
    assert out["if_score"].isna().all()


def test_pca_projections_skips_short_segments():
    """segment 내 관측치 2건 미만이면 skip."""
    feat = _sample_features(1)  # 1건
    out = _compute_pca_projections(feat, pd.DataFrame())
    assert len(out) == 0


def test_pca_projections_segment_independent():
    """segment 별 독립 산출 — A와 B 좌표 독립."""
    feat_a = _sample_features(5)
    feat_b = _sample_features(5)
    feat_b["segment_id"] = "B"
    feat = pd.concat([feat_a, feat_b], ignore_index=True)

    out = _compute_pca_projections(feat, pd.DataFrame())
    assert len(out) == 10
    assert set(out["segment_id"]) == {"A", "B"}


def test_pca_projections_dropna():
    """결측 행은 제외."""
    feat = _sample_features(5)
    feat.loc[2, "transmission_rate"] = float("nan")
    out = _compute_pca_projections(feat, pd.DataFrame())
    # 1행 빠짐
    assert len(out) == 4
