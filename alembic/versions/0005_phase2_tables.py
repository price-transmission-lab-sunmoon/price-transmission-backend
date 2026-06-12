"""0005_phase2_tables

Phase 2 계량 테이블 수동 정의 (feature_spec_DB-PIPELINE_v2 §3.1, autogenerate 금지).
포함 테이블: stationarity_results

* cointegration_results는 0004_add_cointegration_results.py 에서 이미 정의됨.
* stationarity_results만 이 revision 에서 신규 추가.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # db_schema_v5 §stationarity_results 기준
    # UNIQUE (commodity_id, price_col)
    op.create_table(
        "stationarity_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("price_col", sa.String(50), nullable=False),
        sa.Column("n_obs", sa.Integer(), nullable=False),
        # 수준(level) 검정
        sa.Column("level_adf_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("level_adf_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("level_adf_lags", sa.SmallInteger(), nullable=True),
        sa.Column("level_adf_stationary", sa.Boolean(), nullable=True),
        sa.Column("level_kpss_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("level_kpss_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("level_kpss_stationary", sa.Boolean(), nullable=True),
        sa.Column("level_judgment", sa.String(20), nullable=True),
        sa.Column("level_conflict_note", sa.String(50), nullable=True),
        # 차분(diff) 검정
        sa.Column("diff_adf_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("diff_adf_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("diff_kpss_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("diff_kpss_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("diff_judgment", sa.String(20), nullable=True),
        # 최종
        sa.Column("integration_order", sa.SmallInteger(), nullable=False),
        sa.Column("i2_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commodity_id"], ["commodities.commodity_id"],
            name="fk_stationarity_commodity_id_commodities",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"],
            name="fk_stationarity_pipeline_run_id_pipeline_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stationarity_results"),
        sa.UniqueConstraint("commodity_id", "price_col", name="uq_stationarity_commodity_price_col"),
    )


def downgrade() -> None:
    op.drop_table("stationarity_results")
