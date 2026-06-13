"""0003_add_baselines

baselines 테이블 추가 (subperiod_id FK는 0007에서 추가).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "baselines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        # NULL = 전체 기간 기준선; FK to subperiods는 0007에서 추가
        sa.Column("subperiod_id", sa.Integer(), nullable=True),
        sa.Column("normal_transmission_lag", sa.SmallInteger(), nullable=False),
        sa.Column("transmission_elasticity", sa.Numeric(10, 4), nullable=False),
        sa.Column("warmup_end", sa.Date(), nullable=False),   # estimation_start + 48개월
        sa.Column("model_type", sa.String(10), nullable=False),
        sa.Column("estimation_start", sa.Date(), nullable=False),
        sa.Column("estimation_end", sa.Date(), nullable=False),
        sa.Column("n_obs", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["commodity_id"],
            ["commodities.commodity_id"],
            name="fk_baselines_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.segment_id"],
            name="fk_baselines_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name="fk_baselines_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_baselines"),
        sa.UniqueConstraint(
            "commodity_id",
            "segment_id",
            "subperiod_id",
            name="uq_baselines_commodity_segment_subperiod",
        ),
    )


def downgrade() -> None:
    op.drop_table("baselines")
