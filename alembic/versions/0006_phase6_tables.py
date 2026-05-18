"""0006_phase6_tables

Phase 6 계량 테이블 수동 정의 (feature_spec_DB-PIPELINE_v2 §3.1, autogenerate 금지).
포함 테이블: breakpoints, subperiods

* Phase 4 테이블(model_params, irf_data)이 subperiods.id 를 FK 참조하므로
  이 revision 을 Phase 4~5 테이블(0007)보다 먼저 생성한다.
* baselines 도 subperiod_id FK 가 필요하나 0003 에서 이미 컬럼만 선언했으므로
  0007 에서 ALTER TABLE 로 FK 제약을 추가한다.

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
    # ── breakpoints ───────────────────────────────────────────────────────────
    # db_schema_v5 §breakpoints 기준
    # UNIQUE (commodity_id, segment_id)
    op.create_table(
        "breakpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        # Bai-Perron 탐지 결과 — "YYYY-MM" → DATE "YYYY-MM-01" 월초 승격 후 적재 (D-07)
        sa.Column("bp_dates", postgresql.ARRAY(sa.Date()), nullable=True),
        # Chow Test 결과 — 고정 3개 시점 (D-07)
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

    # ── subperiods ────────────────────────────────────────────────────────────
    # db_schema_v5 §subperiods 기준
    # UNIQUE (commodity_id, segment_id, subperiod_index)
    op.create_table(
        "subperiods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("subperiod_index", sa.SmallInteger(), nullable=False),
        # "YYYY-MM" → DATE "YYYY-MM-01" 월초 승격 후 적재 (D-07)
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
