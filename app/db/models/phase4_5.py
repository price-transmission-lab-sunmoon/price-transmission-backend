"""ORM models — Phase 4~5 계량 테이블

frame_spec_backend_vN §8.6 분할 기준:
  model_params (Phase 4)
  irf_data     (Phase 4)
  baselines    (Phase 4) — 0003_add_baselines.py 에서 테이블 정의 완료, ORM만 선언
  granger_results (Phase 5)

db_schema_v5 컬럼명·타입 기준으로 작성.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelParams(Base):
    """Phase 4 VAR/VECM 추정 파라미터 — db_schema_v5 §model_params"""

    __tablename__ = "model_params"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    # NULL = 전체 기간 모형 (Phase 6 완료 전 기본값)
    subperiod_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subperiods.id"))

    model_type: Mapped[str] = mapped_column(String(10), nullable=False)   # 'VAR' | 'VECM'
    lag_selected: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lag_criterion: Mapped[str] = mapped_column(String(10), nullable=False, default="AIC")
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False)
    estimation_start: Mapped[Date] = mapped_column(Date, nullable=False)
    estimation_end: Mapped[Date] = mapped_column(Date, nullable=False)
    cointegrated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    det_order: Mapped[int | None] = mapped_column(SmallInteger)
    coint_rank: Mapped[int | None] = mapped_column(SmallInteger)

    aic: Mapped[float | None] = mapped_column(Numeric(14, 4))
    bic: Mapped[float | None] = mapped_column(Numeric(14, 4))
    log_likelihood: Mapped[float | None] = mapped_column(Numeric(14, 4))

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")


class IrfData(Base):
    """Phase 4 IRF 곡선 데이터 — db_schema_v5 §irf_data"""

    __tablename__ = "irf_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    # NULL = 전체 기간
    subperiod_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subperiods.id"))

    horizon: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    irf_downstream: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    irf_lower_ci: Mapped[float | None] = mapped_column(Numeric(12, 6))
    irf_upper_ci: Mapped[float | None] = mapped_column(Numeric(12, 6))

    # horizon=0 행에만 저장, 나머지 행은 NULL
    irf_peak_horizon: Mapped[int | None] = mapped_column(SmallInteger)
    irf_peak_magnitude: Mapped[float | None] = mapped_column(Numeric(12, 6))

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")


class Baseline(Base):
    """Phase 4 기준선 파라미터 — db_schema_v5 §baselines

    0003_add_baselines.py 에서 테이블 정의 완료.
    ORM 모델만 이 파일에 선언한다.
    """

    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    # NULL = 전체 기간 기준선 (D-15)
    subperiod_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subperiods.id"))

    normal_transmission_lag: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    transmission_elasticity: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    # estimation_start + 48개월 (D-06)
    warmup_end: Mapped[Date] = mapped_column(Date, nullable=False)
    model_type: Mapped[str] = mapped_column(String(10), nullable=False)
    estimation_start: Mapped[Date] = mapped_column(Date, nullable=False)
    estimation_end: Mapped[Date] = mapped_column(Date, nullable=False)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False)

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")


class GrangerResult(Base):
    """Phase 5 Granger 인과 검정 결과 — db_schema_v5 §granger_results

    4구간 품목(groundnuts, banana, orange) 구간 C에만 존재.
    """

    __tablename__ = "granger_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    # DEFAULT 'C' (D-10)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False, default="C")

    direction: Mapped[str] = mapped_column(String(30), nullable=False)  # 'ppi_to_wholesale' | 'wholesale_to_ppi'
    max_lag: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    f_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    significant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 'ppi_to_wholesale' | 'wholesale_to_ppi' | 'bidirectional' | 'none'
    confirmed_direction: Mapped[str | None] = mapped_column(String(30))

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")
