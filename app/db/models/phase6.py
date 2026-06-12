"""ORM models — Phase 6 계량 테이블 (breakpoints, subperiods)."""
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Breakpoint(Base):
    """Phase 6 구조 변화 시점. Chow Test 고정 3개 시점: 2008-01, 2020-01, 2022-01."""

    __tablename__ = "breakpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)

    # Bai-Perron 탐지 시점 목록, 파싱 실패 시 NULL
    bp_dates: Mapped[list | None] = mapped_column(ARRAY(Date))

    # Chow Test 결과 — 고정 3개 시점
    chow_2008_f: Mapped[float | None] = mapped_column(Numeric(10, 4))
    chow_2008_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    chow_2008_sig: Mapped[bool | None] = mapped_column(Boolean)
    chow_2020_f: Mapped[float | None] = mapped_column(Numeric(10, 4))
    chow_2020_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    chow_2020_sig: Mapped[bool | None] = mapped_column(Boolean)
    chow_2022_f: Mapped[float | None] = mapped_column(Numeric(10, 4))
    chow_2022_pvalue: Mapped[float | None] = mapped_column(Numeric(8, 4))
    chow_2022_sig: Mapped[bool | None] = mapped_column(Boolean)

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")


class Subperiod(Base):
    """Phase 6 하위 기간 분할. merged_with_index는 subperiod.id가 아닌 subperiod_index 기준."""

    __tablename__ = "subperiods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commodity_id: Mapped[str] = mapped_column(String(20), ForeignKey("commodities.commodity_id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(10), ForeignKey("segments.segment_id"), nullable=False)
    subperiod_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_start: Mapped[Date] = mapped_column(Date, nullable=False)
    period_end: Mapped[Date] = mapped_column(Date, nullable=False)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False)
    # 60개 미달 시 병합 대상 subperiod_index (NULL = 독립)
    merged_with_index: Mapped[int | None] = mapped_column(SmallInteger)

    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_runs.id"))
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")
