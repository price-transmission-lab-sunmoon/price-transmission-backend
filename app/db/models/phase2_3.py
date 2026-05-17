"""ORM models — Phase 2~3 계량 테이블

frame_spec_backend_vN §8.6 분할 기준:
  stationarity_results (Phase 2)
  cointegration_results (Phase 3)

db_schema_v5 컬럼명·타입 기준으로 작성.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StationarityResult(Base):
    """Phase 2 ADF+KPSS 정상성 검정 결과 — db_schema_v5 §stationarity_results"""

    __tablename__ = "stationarity_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    price_col: Mapped[str] = mapped_column(String(50), nullable=False)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False)

    # 수준(level) 검정
    level_adf_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    level_adf_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    level_adf_lags: Mapped[int | None] = mapped_column(SmallInteger)
    level_adf_stationary: Mapped[bool | None] = mapped_column(Boolean)
    level_kpss_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    level_kpss_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    level_kpss_stationary: Mapped[bool | None] = mapped_column(Boolean)
    level_judgment: Mapped[str | None] = mapped_column(String(20))
    level_conflict_note: Mapped[str | None] = mapped_column(String(50))

    # 차분(diff) 검정 — 비정상 시에만 값 존재
    diff_adf_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    diff_adf_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    diff_kpss_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    diff_kpss_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    diff_judgment: Mapped[str | None] = mapped_column(String(20))

    # 최종
    integration_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    i2_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")


class CointegrationResult(Base):
    """Phase 3 Johansen 공적분 검정 결과 — db_schema_v5 §cointegration_results

    0004_add_cointegration_results.py 에서 테이블 정의 완료.
    ORM 모델만 이 파일에 선언한다.
    """

    __tablename__ = "cointegration_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    upstream_col: Mapped[str] = mapped_column(String(50), nullable=False)
    downstream_col: Mapped[str] = mapped_column(String(50), nullable=False)

    upstream_integration_order: Mapped[int | None] = mapped_column(SmallInteger)
    downstream_integration_order: Mapped[int | None] = mapped_column(SmallInteger)
    integration_order_match: Mapped[bool | None] = mapped_column(Boolean)
    coint_tested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Johansen 검정 (p값은 라이브러리 미제공 → NULL 적재)
    trace_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    trace_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    maxeig_stat: Mapped[float | None] = mapped_column(Numeric(10, 4))
    maxeig_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    coint_rank: Mapped[int | None] = mapped_column(SmallInteger)
    cointegrated: Mapped[bool | None] = mapped_column(Boolean)
    i2_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model_type: Mapped[str | None] = mapped_column(String(10))  # 'VAR' | 'VECM'
    # Phase 5 적재 시 UPDATE로 채워짐 (4구간 구간 C만)
    granger_direction: Mapped[str | None] = mapped_column(String(30))

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")
