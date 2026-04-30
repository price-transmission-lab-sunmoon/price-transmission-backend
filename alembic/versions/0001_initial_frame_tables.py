"""0001_initial_frame_tables

Frame 단계 9개 테이블 수동 정의 (frame_spec §8.9, autogenerate 금지).
포함 테이블: pipeline_runs, data_freshness, commodities, segments,
            external_events, raw_prices, stat_timeseries,
            anomaly_results, asymmetry_results
인덱스·UNIQUE 제약 포함 (db_schema_v3 기준).

Revision ID: 0001
Revises:
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── pipeline_runs (다른 테이블에서 FK 참조하므로 먼저 생성) ─────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("data_up_to", sa.Date(), nullable=False),
        sa.Column("next_run_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("phases_run", postgresql.ARRAY(sa.String(10)), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
        sa.UniqueConstraint("run_date", name="uq_pipeline_runs_run_date"),
    )

    # ── data_freshness ────────────────────────────────────────────────────────
    op.create_table(
        "data_freshness",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_up_to", sa.Date(), nullable=False),
        sa.Column("next_run_date", sa.Date(), nullable=False),
        sa.Column("last_updated", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_data_freshness_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_data_freshness"),
    )

    # ── commodities ───────────────────────────────────────────────────────────
    op.create_table(
        "commodities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("name_kr", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(50), nullable=False),
        sa.Column("cluster", sa.String(30), nullable=True),
        sa.Column("has_wholesale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("route_type", sa.String(10), nullable=False),
        sa.Column("analysis_start", sa.Date(), nullable=True),
        sa.Column("analysis_end", sa.Date(), nullable=True),
        sa.Column("pinksheet_var", sa.String(100), nullable=True),
        sa.Column("hs_code", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_commodities"),
        sa.UniqueConstraint("commodity_id", name="uq_commodities_commodity_id"),
    )

    # ── segments ──────────────────────────────────────────────────────────────
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("label_kr", sa.String(50), nullable=False),
        sa.Column("upstream_col", sa.String(50), nullable=False),
        sa.Column("downstream_col", sa.String(50), nullable=False),
        sa.Column("upstream_label", sa.String(50), nullable=False),
        sa.Column("downstream_label", sa.String(50), nullable=False),
        sa.Column("applies_to", sa.String(10), nullable=False),
        sa.Column("pattern1", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("pattern2", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pattern3", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ml_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id", name="pk_segments"),
        sa.UniqueConstraint("segment_id", name="uq_segments_segment_id"),
    )

    # ── external_events ───────────────────────────────────────────────────────
    op.create_table(
        "external_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_key", sa.String(50), nullable=False),
        sa.Column("label_kr", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("color_hex", sa.String(10), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_external_events"),
        sa.UniqueConstraint("event_key", name="uq_external_events_event_key"),
    )

    # ── raw_prices ────────────────────────────────────────────────────────────
    op.create_table(
        "raw_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("intl_price_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("intl_price_krw", sa.Numeric(14, 4), nullable=True),
        sa.Column("import_price_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("ppi", sa.Numeric(12, 4), nullable=True),
        sa.Column("cpi", sa.Numeric(12, 4), nullable=True),
        sa.Column("wholesale_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("intl_price_krw_idx", sa.Numeric(10, 4), nullable=True),
        sa.Column("import_price_idx", sa.Numeric(10, 4), nullable=True),
        sa.Column("ppi_idx", sa.Numeric(10, 4), nullable=True),
        sa.Column("cpi_idx", sa.Numeric(10, 4), nullable=True),
        sa.Column("wholesale_price_idx", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_raw_prices_commodity_id_commodities"),
        sa.PrimaryKeyConstraint("id", name="pk_raw_prices"),
        sa.UniqueConstraint("commodity_id", "period", name="uq_raw_prices_commodity_id"),
    )
    op.create_index("idx_raw_prices_commodity_period", "raw_prices", ["commodity_id", "period"])

    # ── stat_timeseries ───────────────────────────────────────────────────────
    op.create_table(
        "stat_timeseries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("transmission_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("upstream_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("downstream_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("rolling_mean", sa.Numeric(12, 6), nullable=True),
        sa.Column("rolling_std", sa.Numeric(12, 6), nullable=True),
        sa.Column("zscore", sa.Numeric(10, 4), nullable=True),
        sa.Column("q1", sa.Numeric(12, 6), nullable=True),
        sa.Column("q3", sa.Numeric(12, 6), nullable=True),
        sa.Column("iqr", sa.Numeric(12, 6), nullable=True),
        sa.Column("iqr_lower", sa.Numeric(12, 6), nullable=True),
        sa.Column("iqr_upper", sa.Numeric(12, 6), nullable=True),
        sa.Column("in_warmup_period", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("zscore_w36", sa.Numeric(10, 4), nullable=True),
        sa.Column("zscore_w60", sa.Numeric(10, 4), nullable=True),
        sa.Column("ect_or_spread", sa.Numeric(12, 6), nullable=True),
        sa.Column("ect_type", sa.String(15), nullable=True),
        sa.Column("in_stable_period", sa.Boolean(), nullable=True),
        sa.Column("spread_n2", sa.Numeric(12, 6), nullable=True),
        sa.Column("spread_n3", sa.Numeric(12, 6), nullable=True),
        sa.Column("spread_n6", sa.Numeric(12, 6), nullable=True),
        sa.Column("exchange_rate_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("intl_price_usd_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_stat_timeseries_commodity_id_commodities"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.segment_id"], name="fk_stat_timeseries_segment_id_segments"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_stat_timeseries_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_stat_timeseries"),
        sa.UniqueConstraint("commodity_id", "segment_id", "period", name="uq_stat_ts_commodity_segment_period"),
    )
    # db_schema_v3: period DESC 최신 데이터 조회 최적화
    op.create_index(
        "idx_stat_ts_commodity_segment_period",
        "stat_timeseries",
        ["commodity_id", "segment_id", sa.text("period DESC")],
    )

    # ── anomaly_results ───────────────────────────────────────────────────────
    op.create_table(
        "anomaly_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("pattern_types", postgresql.ARRAY(sa.String(10)), nullable=False),
        sa.Column("primary_pattern", sa.String(10), nullable=False),
        sa.Column("direction_reversal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lag_deviation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pattern1_flag_type", sa.String(20), nullable=True),
        sa.Column("actual_lag", sa.SmallInteger(), nullable=True),
        sa.Column("normal_lag", sa.SmallInteger(), nullable=True),
        sa.Column("transmission_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("zscore_value", sa.Numeric(10, 4), nullable=True),
        sa.Column("zscore_warning", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("zscore_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("iqr_outlier", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("over_transmission", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("under_transmission", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("spread_n3_value", sa.Numeric(12, 6), nullable=True),
        sa.Column("pattern3_n", sa.SmallInteger(), nullable=True),
        sa.Column("stat_detected", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ml_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ml_vote", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("if_anomaly", sa.Boolean(), nullable=True),
        sa.Column("lof_anomaly", sa.Boolean(), nullable=True),
        sa.Column("svm_anomaly", sa.Boolean(), nullable=True),
        sa.Column("confidence_grade", sa.String(15), nullable=False),
        sa.Column("subperiod_id", sa.Integer(), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_anomaly_results_commodity_id_commodities"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.segment_id"], name="fk_anomaly_results_segment_id_segments"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_anomaly_results_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_anomaly_results"),
        sa.UniqueConstraint("commodity_id", "segment_id", "period", name="uq_anomaly_commodity_segment_period"),
    )
    # db_schema_v3 §anomaly_results 인덱스 3종
    op.create_index(
        "idx_anomaly_commodity_period",
        "anomaly_results",
        ["commodity_id", sa.text("period DESC")],
    )
    op.create_index(
        "idx_anomaly_grade",
        "anomaly_results",
        ["confidence_grade", sa.text("period DESC")],
    )
    op.create_index(
        "idx_anomaly_is_new",
        "anomaly_results",
        ["is_new"],
        postgresql_where=sa.text("is_new = TRUE"),
    )

    # ── asymmetry_results ─────────────────────────────────────────────────────
    op.create_table(
        "asymmetry_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commodity_id", sa.String(20), nullable=False),
        sa.Column("segment_id", sa.String(10), nullable=False),
        sa.Column("model_type", sa.String(20), nullable=False),
        sa.Column("alpha_plus", sa.Numeric(10, 6), nullable=True),
        sa.Column("alpha_minus", sa.Numeric(10, 6), nullable=True),
        sa.Column("wald_stat", sa.Numeric(10, 4), nullable=True),
        sa.Column("wald_pvalue", sa.Numeric(8, 4), nullable=True),
        sa.Column("up_coef", sa.Numeric(10, 6), nullable=True),
        sa.Column("down_coef", sa.Numeric(10, 6), nullable=True),
        sa.Column("asymmetry_significant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rocket_feather_direction", sa.String(20), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.commodity_id"], name="fk_asymmetry_results_commodity_id_commodities"),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.segment_id"], name="fk_asymmetry_results_segment_id_segments"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_asymmetry_results_pipeline_run_id_pipeline_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_asymmetry_results"),
        sa.UniqueConstraint("commodity_id", "segment_id", name="uq_asymmetry_commodity_segment"),
    )


def downgrade() -> None:
    op.drop_table("asymmetry_results")
    op.drop_index("idx_anomaly_is_new", table_name="anomaly_results")
    op.drop_index("idx_anomaly_grade", table_name="anomaly_results")
    op.drop_index("idx_anomaly_commodity_period", table_name="anomaly_results")
    op.drop_table("anomaly_results")
    op.drop_index("idx_stat_ts_commodity_segment_period", table_name="stat_timeseries")
    op.drop_table("stat_timeseries")
    op.drop_index("idx_raw_prices_commodity_period", table_name="raw_prices")
    op.drop_table("raw_prices")
    op.drop_table("external_events")
    op.drop_table("segments")
    op.drop_table("commodities")
    op.drop_table("data_freshness")
    op.drop_table("pipeline_runs")
