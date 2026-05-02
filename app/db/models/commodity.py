"""ORM 모델 — commodities, segments, external_events (db_schema_vN §참조 테이블)."""
from sqlalchemy import TIMESTAMP, Boolean, Column, Date, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class Commodity(Base):
    __tablename__ = "commodities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_id = Column(String(20), nullable=False, unique=True)
    name_kr = Column(String(50), nullable=False)
    name_en = Column(String(50), nullable=False)
    cluster = Column(String(30))  # 'grain'|'oil_sugar'|'tropical'|'livestock'|'independent'
    has_wholesale = Column(Boolean, nullable=False, default=False)
    route_type = Column(String(10), nullable=False)  # '3seg'|'4seg'
    analysis_start = Column(Date)
    analysis_end = Column(Date)
    pinksheet_var = Column(String(100))
    hs_code = Column(String(20))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    segment_id = Column(String(10), nullable=False, unique=True)  # 'A','B','C','D','D_prime'
    label_kr = Column(String(50), nullable=False)
    upstream_col = Column(String(50), nullable=False)
    downstream_col = Column(String(50), nullable=False)
    upstream_label = Column(String(50), nullable=False)
    downstream_label = Column(String(50), nullable=False)
    applies_to = Column(String(10), nullable=False)  # 'all'|'3seg'|'4seg'
    pattern1 = Column(Boolean, nullable=False, default=True)
    pattern2 = Column(Boolean, nullable=False, default=False)
    pattern3 = Column(Boolean, nullable=False, default=False)
    ml_applied = Column(Boolean, nullable=False, default=False)


class ExternalEvent(Base):
    __tablename__ = "external_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_key = Column(String(50), nullable=False, unique=True)
    label_kr = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    color_hex = Column(String(10), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
