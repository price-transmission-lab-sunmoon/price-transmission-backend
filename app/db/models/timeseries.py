"""ORM 모델: stat_timeseries, raw_prices, mv_anomaly_density_yearly."""
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
from sqlalchemy.sql import func

from app.db.base import Base


class StatTimeseries(Base):
    __tablename__ = "stat_timeseries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id = Column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    period = Column(Date, nullable=False)  # 월 기준일 (YYYY-MM-01)

    # 전이율
    transmission_rate = Column(Numeric(12, 6))
    upstream_pct = Column(Numeric(12, 6))
    downstream_pct = Column(Numeric(12, 6))

    # 롤링 Z-score + IQR
    rolling_mean = Column(Numeric(12, 6))
    rolling_std = Column(Numeric(12, 6))
    zscore = Column(Numeric(10, 4))
    q1 = Column(Numeric(12, 6))
    q3 = Column(Numeric(12, 6))
    iqr = Column(Numeric(12, 6))
    iqr_lower = Column(Numeric(12, 6))
    iqr_upper = Column(Numeric(12, 6))
    in_warmup_period = Column(Boolean, nullable=False, default=False)

    # 로버스트니스
    zscore_w36 = Column(Numeric(10, 4))
    zscore_w60 = Column(Numeric(10, 4))

    # ECT 또는 로그 수준 스프레드 (패턴 3)
    ect_or_spread = Column(Numeric(12, 6))
    ect_type = Column(String(15))  # 'ECT'|'log_spread'

    in_stable_period = Column(Boolean)
    spread_n2 = Column(Numeric(12, 6))
    spread_n3 = Column(Numeric(12, 6))
    spread_n6 = Column(Numeric(12, 6))

    # 외생 피처
    exchange_rate_pct = Column(Numeric(12, 6))
    intl_price_usd_pct = Column(Numeric(12, 6))

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "segment_id", "period", name="uq_stat_ts_commodity_segment_period"),
        Index("idx_stat_ts_commodity_segment_period", "commodity_id", "segment_id", text("period DESC")),
    )


class RawPrice(Base):
    __tablename__ = "raw_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    period = Column(Date, nullable=False)  # 월 기준일 (YYYY-MM-01)

    # 원본값
    intl_price_usd = Column(Numeric(14, 4))
    intl_price_krw = Column(Numeric(14, 4))
    import_price_usd = Column(Numeric(14, 4))
    exchange_rate = Column(Numeric(10, 4))
    ppi = Column(Numeric(12, 4))
    cpi = Column(Numeric(12, 4))
    wholesale_price = Column(Numeric(14, 4))

    # 2020=100 지수 환산값
    intl_price_krw_idx = Column(Numeric(10, 4))
    import_price_idx = Column(Numeric(10, 4))
    ppi_idx = Column(Numeric(10, 4))
    cpi_idx = Column(Numeric(10, 4))
    wholesale_price_idx = Column(Numeric(10, 4))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("commodity_id", "period", name="uq_raw_prices_commodity_period"),
        Index("idx_raw_prices_commodity_period", "commodity_id", "period"),
    )


class MvAnomalyDensityYearly(Base):
    """연도별 이상 밀도 머티리얼라이즈드 뷰. 읽기 전용, REFRESH MATERIALIZED VIEW로 갱신."""
    __tablename__ = "mv_anomaly_density_yearly"

    commodity_id = Column(String(20), primary_key=True)
    segment_id = Column(String(10), primary_key=True)
    year = Column(SmallInteger, primary_key=True)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    reference_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_mv_anomaly_density", "commodity_id", "segment_id", "year"),
    )
