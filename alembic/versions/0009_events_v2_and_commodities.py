"""0009_events_v2_and_commodities

external_events에 commodities 컬럼 추가 + 시드 v2로 교체.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-21
"""
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str = "0008"
branch_labels: str | None = None
depends_on: str | None = None


EVENTS_V2 = [
    (
        "E1_financial_crisis_2008", "2008 글로벌 금융위기",
        date(2008, 7, 1), date(2009, 1, 31), "#F97316",
        ["wheat", "maize", "soybean", "palmoil", "sugar", "coffee", "beef", "groundnuts", "banana", "orange"],
    ),
    (
        "E6_russia_drought_2010", "2010 러시아 가뭄·수출 금지",
        date(2010, 8, 1), date(2011, 6, 30), "#A855F7",
        ["wheat", "maize", "soybean", "palmoil", "sugar", "coffee", "beef"],
    ),
    (
        "E9_elnino_2015", "2015-16 역대급 엘니뇨",
        date(2015, 9, 1), date(2016, 6, 30), "#38BDF8",
        ["maize", "soybean", "palmoil", "sugar", "coffee", "beef"],
    ),
    (
        "E2_covid19_2020", "2020 COVID-19 팬데믹",
        date(2020, 2, 1), date(2020, 6, 30), "#22C55E",
        ["wheat", "maize", "soybean", "palmoil", "sugar", "coffee", "beef", "groundnuts", "banana", "orange"],
    ),
    (
        "E4_ukraine_war_2022", "2022 우크라이나 전쟁",
        date(2022, 2, 1), date(2022, 10, 31), "#EF4444",
        ["wheat", "maize", "soybean", "palmoil"],
    ),
]


def upgrade() -> None:
    op.add_column(
        "external_events",
        sa.Column("commodities", postgresql.ARRAY(sa.String(20)), nullable=True),
    )

    op.execute("DELETE FROM external_events")

    conn = op.get_bind()
    for key, label, sd, ed, color, comms in EVENTS_V2:
        conn.execute(
            sa.text(
                """
                INSERT INTO external_events (event_key, label_kr, start_date, end_date, color_hex, commodities)
                VALUES (:k, :l, :sd, :ed, :c, :cm)
                """
            ),
            {"k": key, "l": label, "sd": sd, "ed": ed, "c": color, "cm": comms},
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM external_events WHERE event_key IN ("
        "'E1_financial_crisis_2008','E6_russia_drought_2010','E9_elnino_2015',"
        "'E2_covid19_2020','E4_ukraine_war_2022')"
    )
    op.drop_column("external_events", "commodities")
