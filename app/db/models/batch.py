"""ORM 모델 — pipeline_runs, data_freshness (db_schema_v3 §배치 관리 테이블)."""
from sqlalchemy import (
    Column, Date, ForeignKey, Integer, String, Text, TIMESTAMP, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from app.db.base import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False)
    data_up_to = Column(Date, nullable=False)
    next_run_date = Column(Date)
    status = Column(String(20), nullable=False, default="running")  # 'running'|'completed'|'failed'
    phases_run = Column(ARRAY(String(10)))
    error_message = Column(Text)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint("run_date", name="uq_pipeline_runs_run_date"),
    )


class DataFreshness(Base):
    __tablename__ = "data_freshness"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_up_to = Column(Date, nullable=False)
    next_run_date = Column(Date, nullable=False)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
