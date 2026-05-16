"""0004_add_cointegration_results

cointegration_results 테이블 추가 — feat/be-api-reference 임시 정의.

⚠️  feat/pipeline-phase2-3 착수 시 중복 충돌 주의.
    (feature_spec_API-REF_v4 §2, frame_spec_backend_vN §8.6).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cointegration_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("upstream_col", sa.String(50), nullable=False),
        sa.Column("downstream_col", sa.String(50), nullable=False),
        sa.Column("upstream_integration_order", sa.SmallInteger(), nullable=True),
        sa.Column("downstream_integration_order", sa.SmallInteger(), nullable=True),
        sa.Column("integration_order_match", sa.Boolean(), nullable=True),
        sa.Column(
            "coint_tested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("trace_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("trace_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("maxeig_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("maxeig_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("coint_rank", sa.SmallInteger(), nullable=True),
        sa.Column("cointegrated", sa.Boolean(), nullable=True),
        sa.Column(
            "i2_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("model_type", sa.String(10), nullable=True),   # 'VAR' | 'VECM'
        sa.Column("granger_direction", sa.String(30), nullable=True),
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
            name="fk_coint_results_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.segment_id"],
            name="fk_coint_results_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name="fk_coint_results_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cointegration_results"),
        sa.UniqueConstraint(
            "commodity_id",
            "segment_id",
            name="uq_coint_results_commodity_segment",
        ),
    )


def downgrade() -> None:
    op.drop_table("cointegration_results")
