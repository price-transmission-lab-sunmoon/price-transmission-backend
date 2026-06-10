"""0002_seed_reference_data

commodities 10행 + segments 5행 + external_events 5행 시드 적재.
출처: db_schema_vN §초기 데이터 (frame_spec_vN §8.9, §8.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── commodities 10행 (db_schema_vN §commodities 초기 데이터) ─────────────
    conn.execute(
        sa.text("""
            INSERT INTO commodities (commodity_id, name_kr, name_en, cluster, has_wholesale, route_type)
            VALUES
                ('wheat',      '밀',    'Wheat',      'grain',       false, '3seg'),
                ('maize',      '옥수수', 'Maize',      'grain',       false, '3seg'),
                ('soybean',    '대두',  'Soybean',    'grain',       false, '3seg'),
                ('palm_oil',   '팜유',  'Palm Oil',   'oil_sugar',   false, '3seg'),
                ('sugar',      '설탕',  'Sugar',      'oil_sugar',   false, '3seg'),
                ('coffee',     '커피',  'Coffee',     'tropical',    false, '3seg'),
                ('beef',       '소고기', 'Beef',       'livestock',   false, '3seg'),
                ('groundnuts', '땅콩',  'Groundnuts', 'independent', true,  '4seg'),
                ('banana',     '바나나', 'Banana',     'tropical',    true,  '4seg'),
                ('orange',     '오렌지', 'Orange',     'independent', true,  '4seg')
            ON CONFLICT (commodity_id) DO NOTHING
        """)
    )

    # ── segments 5행 (db_schema_vN §segments 초기 데이터) ────────────────────
    conn.execute(
        sa.text("""
            INSERT INTO segments
                (segment_id, label_kr, upstream_col, downstream_col,
                 upstream_label, downstream_label, applies_to,
                 pattern1, pattern2, pattern3, ml_applied)
            VALUES
                ('A',       '구간 A (국제가→수입단가)',
                 'intl_price_krw',   'import_price_usd',
                 '국제가 (원화 환산)', '수입단가',
                 'all',   true,  true,  false, true),
                ('B',       '구간 B (수입단가→PPI)',
                 'import_price_usd', 'ppi',
                 '수입단가',          'PPI',
                 'all',   true,  true,  true,  true),
                ('C',       '구간 C (PPI→도매가)',
                 'ppi',              'wholesale_price',
                 'PPI',              '도매가',
                 '4seg',  true,  false, false, false),
                ('D',       '구간 D (도매가→CPI)',
                 'wholesale_price',  'cpi',
                 '도매가',            'CPI',
                 '4seg',  true,  false, false, false),
                ('D_prime', '구간 D′ (PPI→CPI)',
                 'ppi',              'cpi',
                 'PPI',              'CPI',
                 '3seg',  true,  false, false, false)
            ON CONFLICT (segment_id) DO NOTHING
        """)
    )

    # ── external_events 5행 (db_schema_vN §external_events 초기 데이터) ──────
    conn.execute(
        sa.text("""
            INSERT INTO external_events (event_key, label_kr, start_date, end_date, color_hex)
            VALUES
                ('financial_crisis_2008',     '2008 금융위기',
                 '2008-07-01', '2009-03-31', '#F97316'),
                ('covid19_2020',              '2020 코로나19',
                 '2020-02-01', '2021-06-30', '#22C55E'),
                ('brazil_frost_2021',         '2021~22 브라질 서리',
                 '2021-07-01', '2022-03-31', '#38BDF8'),
                ('ukraine_2022',              '2022 우크라이나 사태',
                 '2022-02-01', '2022-10-31', '#EF4444'),
                ('indonesia_palmoil_2022',    '2022 인도네시아 팜유 수출 규제',
                 '2022-04-01', '2022-05-31', '#FB923C')
            ON CONFLICT (event_key) DO NOTHING
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM external_events WHERE event_key IN ('financial_crisis_2008','covid19_2020','brazil_frost_2021','ukraine_2022','indonesia_palmoil_2022')"))
    conn.execute(sa.text("DELETE FROM segments WHERE segment_id IN ('A','B','C','D','D_prime')"))
    conn.execute(sa.text("DELETE FROM commodities WHERE commodity_id IN ('wheat','maize','soybean','palm_oil','sugar','coffee','beef','groundnuts','banana','orange')"))
