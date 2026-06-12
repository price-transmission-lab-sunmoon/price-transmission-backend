"""0007_phase4_5_tables

model_params, irf_data, granger_results 테이블 추가.
baselines(0003)에 subperiod_id FK 제약 추가.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-17
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "model_params",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        # NULL = 전체 기간 모형
        sa.Column("subperiod_id", sa.Integer(), nullable=True),
        sa.Column("model_type", sa.String(10), nullable=False),
        sa.Column("lag_selected", sa.SmallInteger(), nullable=False),
        sa.Column("lag_criterion", sa.String(10), nullable=False, server_default="AIC"),
        sa.Column("n_obs", sa.Integer(), nullable=False),
        sa.Column("estimation_start", sa.Date(), nullable=False),
        sa.Column("estimation_end", sa.Date(), nullable=False),
        sa.Column("cointegrated", sa.Boolean(), nullable=False),
        sa.Column("det_order", sa.SmallInteger(), nullable=True),
        sa.Column("coint_rank", sa.SmallInteger(), nullable=True),
        sa.Column("aic", sa.Numeric(14, 4), nullable=True),
        sa.Column("bic", sa.Numeric(14, 4), nullable=True),
        sa.Column("log_likelihood", sa.Numeric(14, 4), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_model_params_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.segment_id"],
            name="fk_model_params_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["subperiod_id"], ["subperiods.id"],
            name="fk_model_params_subperiod_id_subperiods",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_model_params_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_params"),
        sa.UniqueConstraint(
            "commodity_id", "segment_id", "subperiod_id",
            name="uq_model_params_commodity_segment_subperiod",
        ),
    )

    op.create_table(
        "irf_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        # NULL = 전체 기간
        sa.Column("subperiod_id", sa.Integer(), nullable=True),
        sa.Column("horizon", sa.SmallInteger(), nullable=False),
        sa.Column("irf_downstream", sa.Numeric(12, 6), nullable=False),
        sa.Column("irf_lower_ci", sa.Numeric(12, 6), nullable=True),
        sa.Column("irf_upper_ci", sa.Numeric(12, 6), nullable=True),
        # horizon=0 행에만 저장, 나머지 NULL
        sa.Column("irf_peak_horizon", sa.SmallInteger(), nullable=True),
        sa.Column("irf_peak_magnitude", sa.Numeric(12, 6), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_irf_data_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.segment_id"],
            name="fk_irf_data_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["subperiod_id"], ["subperiods.id"],
            name="fk_irf_data_subperiod_id_subperiods",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_irf_data_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_irf_data"),
        sa.UniqueConstraint(
            "commodity_id", "segment_id", "subperiod_id", "horizon",
            name="uq_irf_commodity_segment_subperiod_horizon",
        ),
    )
    op.create_index(
        "idx_irf_commodity_segment",
        "irf_data",
        ["commodity_id", "segment_id", "subperiod_id"],
    )

    op.create_table(
        "granger_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False, server_default="C"),
        sa.Column("direction", sa.String(30), nullable=False),
        sa.Column("max_lag", sa.SmallInteger(), nullable=False),
        sa.Column("f_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("significant", sa.Boolean(), nullable=False),
        sa.Column("confirmed_direction", sa.String(30), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_granger_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["segments.segment_id"],
            name="fk_granger_segment_id_segments",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_granger_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_granger_results"),
        sa.UniqueConstraint(
            "commodity_id", "segment_id", "direction",
            name="uq_granger_commodity_segment_direction",
        ),
    )

    # 0003에서 컬럼만 선언, subperiods(0006) 생성 후 FK 추가
    op.create_foreign_key(
        "fk_baselines_subperiod_id_subperiods",
        "baselines", "subperiods",
        ["subperiod_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_baselines_subperiod_id_subperiods", "baselines", type_="foreignkey")
    op.drop_index("idx_irf_commodity_segment", table_name="irf_data")
    op.drop_table("granger_results")
    op.drop_table("irf_data")
    op.drop_table("model_params")
