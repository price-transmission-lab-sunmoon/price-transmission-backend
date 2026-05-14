"""ORM 모델 — baselines, cointegration_results (임시 정의).

⚠️ 임시 정의: feat/pipeline-phase4-5(baselines), feat/pipeline-phase2-3(cointegration_results)
착수 시 중복 충돌 방지 조율 필요 (feature_spec_API-REF_v4 §2, frame_spec_backend_vN §8.6).
"""
from __future__ import annotations

from sqlalchemy import TIMESTAMP, Boolean, Column, Date, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.sql import func

from app.db.base import Base


class Baseline(Base):
    """db_schema_vN §baselines — Phase 4 기준선 파라미터."""
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    subperiod_id = Column(Integer, nullable=True)  # NULL = 전체 기간 기준선 (D-15)

    normal_transmission_lag = Column(SmallInteger, nullable=False)
    transmission_elasticity = Column(Numeric(10, 4), nullable=False)
    warmup_end = Column(Date, nullable=False)  # estimation_start + 48개월 (D-06)
    model_type = Column(String(10), nullable=False)  # 'VAR' | 'VECM'
    estimation_start = Column(Date, nullable=False)
    estimation_end = Column(Date, nullable=False)
    n_obs = Column(Integer, nullable=False)

    pipeline_run_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class CointegrationResult(Base):
    """db_schema_vN §cointegration_results — Phase 3 Johansen 공적분 검정 결과."""
    __tablename__ = "cointegration_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    upstream_col = Column(String(50), nullable=False)
    downstream_col = Column(String(50), nullable=False)

    upstream_integration_order = Column(SmallInteger, nullable=True)
    downstream_integration_order = Column(SmallInteger, nullable=True)
    integration_order_match = Column(Boolean, nullable=True)
    coint_tested = Column(Boolean, nullable=False, default=False)

    trace_stat = Column(Numeric(10, 4), nullable=True)
    trace_pvalue = Column(Numeric(8, 4), nullable=True)
    maxeig_stat = Column(Numeric(10, 4), nullable=True)
    maxeig_pvalue = Column(Numeric(8, 4), nullable=True)
    coint_rank = Column(SmallInteger, nullable=True)
    cointegrated = Column(Boolean, nullable=True)
    i2_flag = Column(Boolean, nullable=False, default=False)

    model_type = Column(String(10), nullable=True)  # 'VAR' | 'VECM'
    granger_direction = Column(String(30), nullable=True)

    pipeline_run_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
