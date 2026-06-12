"""0008_ml_score_projection_tables

ml_scores, ml_projections 테이블 추가 (Phase 7-ML).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ml_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),

        sa.Column("if_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("if_anomaly", sa.Boolean(), nullable=True),
        sa.Column("if_percentile", sa.Numeric(6, 2), nullable=True),

        sa.Column("lof_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("lof_anomaly", sa.Boolean(), nullable=True),
        sa.Column("lof_percentile", sa.Numeric(6, 2), nullable=True),

        sa.Column("svm_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("svm_anomaly", sa.Boolean(), nullable=True),
        sa.Column("svm_percentile", sa.Numeric(6, 2), nullable=True),

        sa.Column("ml_vote", sa.SmallInteger(), nullable=True),
        sa.Column("ml_detected", sa.Boolean(), nullable=True),

        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_ml_scores_commodity_id_commodities"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.segment_id"], name="fk_ml_scores_segment_id_segments"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_ml_scores_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_ml_scores"),
        sa.UniqueConstraint("commodity_id", "segment_id", "period", name="uq_ml_scores_commodity_segment_period"),
    )
    op.create_index(
        "idx_ml_scores_commodity_segment",
        "ml_scores",
        ["commodity_id", "segment_id", sa.text("period DESC")],
    )

    op.create_table(
        "ml_projections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),

        sa.Column("model_name", sa.String(20), nullable=False),
        sa.Column("projection_method", sa.String(20), nullable=False),

        sa.Column("x_value", sa.Numeric(12, 6), nullable=False),
        sa.Column("y_value", sa.Numeric(12, 6), nullable=False),
        sa.Column("x_label", sa.String(50), nullable=True),
        sa.Column("y_label", sa.String(50), nullable=True),

        sa.Column("anomaly_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=True),

        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_ml_proj_commodity_id_commodities"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.segment_id"], name="fk_ml_proj_segment_id_segments"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_ml_proj_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_ml_projections"),
        sa.UniqueConstraint(
            "commodity_id", "segment_id", "period", "model_name", "projection_method",
            name="uq_ml_projections",
        ),
    )
    op.create_index(
        "idx_ml_proj_commodity_segment_model",
        "ml_projections",
        ["commodity_id", "segment_id", "model_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_ml_proj_commodity_segment_model", table_name="ml_projections")
    op.drop_table("ml_projections")
    op.drop_index("idx_ml_scores_commodity_segment", table_name="ml_scores")
    op.drop_table("ml_scores")
