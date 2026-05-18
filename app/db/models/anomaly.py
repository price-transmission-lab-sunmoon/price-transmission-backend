"""ORM 모델 — anomaly_results, asymmetry_results + feat/be-api-panel 추가 모델
(db_schema_vN §이상 탐지·ML·Phase 4~6 테이블).
"""
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
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
        # db_schema_vN §anomaly_results 인덱스
        Index("idx_anomaly_commodity_period", "commodity_id", text("period DESC")),
        Index("idx_anomaly_grade", "confidence_grade", text("period DESC")),
        Index(
            "idx_anomaly_is_new",
            "is_new",
            postgresql_where=text("is_new = TRUE"),
        ),
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


# ── Phase 6 테이블 (feat/be-api-panel에서 ORM 추가) ───────────────────────────

class Subperiod(Base):
    """db_schema_vN §subperiods — Phase 6 하위 기간 분할."""
    __tablename__ = "subperiods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    subperiod_index = Column(SmallInteger, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    n_obs = Column(Integer, nullable=False)
    merged_with_index = Column(SmallInteger)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "subperiod_index", name="uq_subperiods"),
    )


class Breakpoint(Base):
    """db_schema_vN §breakpoints — Phase 6 구조 변화 시점 (D-16: bp_dates 출처)."""
    __tablename__ = "breakpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)

    bp_dates = Column(ARRAY(Date))  # Bai-Perron 탐지 시점 목록

    # Chow Test 결과 (고정 3개 시점)
    chow_2008_f = Column(Numeric(10, 4))
    chow_2008_pvalue = Column(Numeric(8, 4))
    chow_2008_sig = Column(Boolean)
    chow_2020_f = Column(Numeric(10, 4))
    chow_2020_pvalue = Column(Numeric(8, 4))
    chow_2020_sig = Column(Boolean)
    chow_2022_f = Column(Numeric(10, 4))
    chow_2022_pvalue = Column(Numeric(8, 4))
    chow_2022_sig = Column(Boolean)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", name="uq_breakpoints"),
    )


# ── Phase 4 테이블 (feat/be-api-panel에서 ORM 추가) ───────────────────────────

class Baseline(Base):
    """db_schema_vN §baselines — Phase 4 기준선 파라미터.

    D-15: subperiod_id IS NULL 조건으로 전체 기간 기준선만 API에 노출.
    """
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    subperiod_id = Column(Integer, ForeignKey("subperiods.id"))  # NULL = 전체 기간

    normal_transmission_lag = Column(SmallInteger, nullable=False)  # → API normal_lag
    transmission_elasticity = Column(Numeric(10, 4), nullable=False)
    warmup_end = Column(Date, nullable=False)
    model_type = Column(String(10), nullable=False)   # 'VAR'|'VECM'
    estimation_start = Column(Date, nullable=False)
    estimation_end = Column(Date, nullable=False)
    n_obs = Column(Integer, nullable=False)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "subperiod_id", name="uq_baselines"),
    )


class IRFData(Base):
    """db_schema_vN §irf_data — Phase 4 IRF 곡선.

    irf_peak_horizon·irf_peak_magnitude 는 horizon=0 행에만 저장.
    """
    __tablename__ = "irf_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    subperiod_id = Column(Integer, ForeignKey("subperiods.id"))  # NULL = 전체 기간

    horizon = Column(SmallInteger, nullable=False)         # 0~24
    irf_downstream = Column(Numeric(12, 6), nullable=False)
    irf_lower_ci = Column(Numeric(12, 6))
    irf_upper_ci = Column(Numeric(12, 6))

    irf_peak_horizon = Column(SmallInteger)        # horizon=0 행에만
    irf_peak_magnitude = Column(Numeric(12, 6))    # horizon=0 행에만

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "subperiod_id", "horizon", name="uq_irf_data"),
        Index("idx_irf_commodity_segment", "commodity_id", "segment_id", "subperiod_id"),
    )


# ── Phase 2~3 테이블 (최소 참조용, feat/be-db-pipeline에서 migration 작성) ────

class CointegrationResult(Base):
    """db_schema_vN §cointegration_results — Phase 3 Johansen 공적분 검정 결과.

    UNIQUE (commodity_id, segment_id) — subperiod_id 없음, 전체 기간 단일 행.
    /detail stat_metrics.cointegrated·model_type 출처.
    """
    __tablename__ = "cointegration_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    upstream_col = Column(String(50), nullable=False)
    downstream_col = Column(String(50), nullable=False)

    upstream_integration_order = Column(SmallInteger)
    downstream_integration_order = Column(SmallInteger)
    integration_order_match = Column(Boolean)
    coint_tested = Column(Boolean, nullable=False, server_default=text("FALSE"))

    # Johansen 검정 결과
    trace_stat = Column(Numeric(10, 4))
    trace_pvalue = Column(Numeric(8, 4))
    maxeig_stat = Column(Numeric(10, 4))
    maxeig_pvalue = Column(Numeric(8, 4))
    coint_rank = Column(SmallInteger)
    cointegrated = Column(Boolean)
    i2_flag = Column(Boolean, nullable=False, server_default=text("FALSE"))

    model_type = Column(String(10))   # 'VAR'|'VECM'
    granger_direction = Column(String(30))

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", name="uq_cointegration_results"),
    )


# ── Phase 7-ML 테이블 (feat/be-api-panel에서 ORM 추가) ────────────────────────

class MLScore(Base):
    """db_schema_vN §ml_scores — Phase 7-ML 모델별 이상 점수.

    조인 키: (commodity_id, segment_id, period) — anomaly_results와 FK 없음.
    """
    __tablename__ = "ml_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    period = Column(Date, nullable=False)

    if_score = Column(Numeric(10, 6))
    if_anomaly = Column(Boolean)
    if_percentile = Column(Numeric(6, 2))

    lof_score = Column(Numeric(10, 6))
    lof_anomaly = Column(Boolean)
    lof_percentile = Column(Numeric(6, 2))

    svm_score = Column(Numeric(10, 6))
    svm_anomaly = Column(Boolean)
    svm_percentile = Column(Numeric(6, 2))

    ml_vote = Column(SmallInteger)
    ml_detected = Column(Boolean)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "period", name="uq_ml_scores"),
        Index("idx_ml_scores_commodity_segment", "commodity_id", "segment_id", text("period DESC")),
    )


class MLProjection(Base):
    """db_schema_vN §ml_projections — Phase 7-ML ML 결과맵 2D 투영.

    OI-15 보류: projection_method 확정 대기.
    """
    __tablename__ = "ml_projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    period = Column(Date, nullable=False)

    model_name = Column(String(20), nullable=False)       # 'isolation_forest'|'lof'|'ocsvm'
    projection_method = Column(String(20), nullable=False) # 'pca'|'feature_direct'

    x_value = Column(Numeric(12, 6), nullable=False)
    y_value = Column(Numeric(12, 6), nullable=False)
    x_label = Column(String(50))
    y_label = Column(String(50))

    anomaly_score = Column(Numeric(10, 6))
    is_anomaly = Column(Boolean)

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "commodity_id", "segment_id", "period", "model_name", "projection_method",
            name="uq_ml_projections",
        ),
        Index("idx_ml_proj_commodity_segment_model", "commodity_id", "segment_id", "model_name"),
    )
