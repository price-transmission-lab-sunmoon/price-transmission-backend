"""0006_phase6_tables

breakpoints, subperiods 테이블 추가 (0007의 FK 참조 대상이므로 먼저 생성).

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "breakpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        # Bai-Perron 탐지 결과 — "YYYY-MM" → DATE "YYYY-MM-01" 월초 승격 후 적재
        sa.Column("bp_dates", postgresql.ARRAY(sa.Date()), nullable=True),
        # Chow Test 결과 — 고정 3개 시점
        sa.Column("chow_2008_f", sa.Numeric(10, 4), nullable=True),
        sa.Column("chow_2008_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("chow_2008_sig", sa.Boolean(), nullable=True),
        sa.Column("chow_2020_f", sa.Numeric(10, 4), nullable=True),
        sa.Column("chow_2020_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("chow_2020_sig", sa.Boolean(), nullable=True),
        sa.Column("chow_2022_f", sa.Numeric(10, 4), nullable=True),
        sa.Column("chow_2022_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("chow_2022_sig", sa.Boolean(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_breakpoints_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.segment_id"],
            name="fk_breakpoints_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_breakpoints_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_breakpoints"),
        sa.UniqueConstraint("commodity_id", "segment_id", name="uq_breakpoints_commodity_segment"),
    )

    op.create_table(
        "subperiods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("subperiod_index", sa.SmallInteger(), nullable=False),
        # "YYYY-MM" → DATE "YYYY-MM-01" 월초 승격 후 적재
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("n_obs", sa.Integer(), nullable=False),
        # 60개 미달 시 병합 대상 subperiod_index (NULL = 독립)
        sa.Column("merged_with_index", sa.SmallInteger(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_subperiods_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.segment_id"],
            name="fk_subperiods_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_subperiods_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subperiods"),
        sa.UniqueConstraint(
            "commodity_id", "segment_id", "subperiod_index",
            name="uq_subperiods_commodity_segment_index",
        ),
    )


def downgrade() -> None:
    op.drop_table("subperiods")
    op.drop_table("breakpoints")
