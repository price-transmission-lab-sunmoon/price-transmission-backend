"""ORM 모델 — anomaly_results, asymmetry_results (db_schema_v3 §이상 탐지 테이블)."""
from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, Numeric, SmallInteger,
    String, TIMESTAMP, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from app.db.base import Base


class AnomalyResult(Base):
    __tablename__ = "anomaly_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    period = Column(Date, nullable=False)  # 월 기준일 (YYYY-MM-01)

    # 패턴
    pattern_types = Column(ARRAY(String(10)), nullable=False)
    primary_pattern = Column(String(10), nullable=False)

    # 패턴 1 세부
    direction_reversal = Column(Boolean, nullable=False, default=False)
    lag_deviation = Column(Boolean, nullable=False, default=False)
    pattern1_flag_type = Column(String(20))  # 'direction_reversal'|'lag_deviation'|'both'
    actual_lag = Column(SmallInteger)
    normal_lag = Column(SmallInteger)

    # 패턴 2 세부
    transmission_rate = Column(Numeric(12, 6))
    zscore_value = Column(Numeric(10, 4))
    zscore_warning = Column(Boolean, nullable=False, default=False)
    zscore_alert = Column(Boolean, nullable=False, default=False)
    iqr_outlier = Column(Boolean, nullable=False, default=False)
    over_transmission = Column(Boolean, nullable=False, default=False)
    under_transmission = Column(Boolean, nullable=False, default=False)

    # 패턴 3 세부
    spread_n3_value = Column(Numeric(12, 6))
    pattern3_n = Column(SmallInteger)

    # 통계 탐지
    stat_detected = Column(Boolean, nullable=False, default=True)

    # ML 판정
    ml_detected = Column(Boolean, nullable=False, default=False)
    ml_vote = Column(SmallInteger, nullable=False, default=0)
    if_anomaly = Column(Boolean)
    lof_anomaly = Column(Boolean)
    svm_anomaly = Column(Boolean)

    # 신뢰도 등급 (D-02: NOT NULL)
    confidence_grade = Column(String(15), nullable=False)  # 'high'|'medium'|'reference'

    subperiod_id = Column(Integer)  # feat/pipeline-phase6-7에서 FK 추가
    is_new = Column(Boolean, nullable=False, default=False)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "period", name="uq_anomaly_commodity_segment_period"),
    )


class AsymmetryResult(Base):
    __tablename__ = "asymmetry_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)

    model_type = Column(String(20), nullable=False)  # 'TECM'|'asymmetric_VAR'

    # TECM 결과
    alpha_plus = Column(Numeric(10, 6))
    alpha_minus = Column(Numeric(10, 6))
    wald_stat = Column(Numeric(10, 4))
    wald_pvalue = Column(Numeric(8, 4))

    # 비대칭 VAR 결과
    up_coef = Column(Numeric(10, 6))
    down_coef = Column(Numeric(10, 6))

    # 공통 판정
    asymmetry_significant = Column(Boolean, nullable=False, default=False)
    rocket_feather_direction = Column(String(20))  # 'upward_stronger'|'downward_stronger'|NULL

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", name="uq_asymmetry_commodity_segment"),
    )
