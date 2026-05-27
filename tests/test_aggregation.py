"""app.services.aggregation 단위 테스트 — granularity 집계 + 이상 밀도.

stream/raw_prices 중복 제거 시 동작 보존을 고정하기 위한 특성화 테스트.
실 DB 불필요 (순수 함수).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.aggregation import (
    aggregate_by_granularity,
    build_anomaly_density,
    quarter_key,
    quarter_last_month,
)

# ── 스트림 필드 셋 (기존 _aggregate_monthly_points 동작 복제) ──────────────────
_STREAM_KW = dict(
    avg_fields=("transmission_rate", "upstream_pct", "downstream_pct"),
    any_fields=("in_warmup_period",),
    concat_fields=("anomaly_ids",),
)


def _pt(y, m, tr, warmup=False, ids=None):
    return {
        "period": date(y, m, 1),
        "transmission_rate": tr,
        "upstream_pct": tr,
        "downstream_pct": tr,
        "in_warmup_period": warmup,
        "anomaly_ids": ids or [],
    }


# ── quarter 헬퍼 ──────────────────────────────────────────────────────────────

def test_quarter_key():
    assert quarter_key(date(2022, 1, 1)) == (2022, 0)
    assert quarter_key(date(2022, 3, 1)) == (2022, 0)
    assert quarter_key(date(2022, 4, 1)) == (2022, 1)
    assert quarter_key(date(2022, 12, 1)) == (2022, 3)


def test_quarter_last_month():
    assert quarter_last_month(2022, 0) == date(2022, 3, 1)
    assert quarter_last_month(2022, 3) == date(2022, 12, 1)


# ── monthly passthrough ───────────────────────────────────────────────────────

def test_monthly_passthrough_identity():
    monthly = [_pt(2022, 1, 1.0), _pt(2022, 2, 2.0)]
    out = aggregate_by_granularity(monthly, "monthly", **_STREAM_KW)
    assert out is monthly  # 원본 그대로


# ── quarterly 집계 ────────────────────────────────────────────────────────────

def test_quarterly_avg_and_period():
    monthly = [_pt(2022, 1, 10.0), _pt(2022, 2, 20.0), _pt(2022, 3, 30.0)]
    out = aggregate_by_granularity(monthly, "quarterly", **_STREAM_KW)
    assert len(out) == 1
    assert out[0]["period"] == date(2022, 3, 1)  # 분기 마지막 월
    assert out[0]["transmission_rate"] == 20.0   # (10+20+30)/3


def test_quarterly_any_flag_and_concat_ids():
    monthly = [
        _pt(2022, 1, 1.0, warmup=False, ids=[1]),
        _pt(2022, 2, 2.0, warmup=True, ids=[2, 3]),
    ]
    out = aggregate_by_granularity(monthly, "quarterly", **_STREAM_KW)
    assert out[0]["in_warmup_period"] is True       # any()
    assert out[0]["anomaly_ids"] == [1, 2, 3]       # 평탄화 결합


# ── None 처리 ─────────────────────────────────────────────────────────────────

def test_avg_ignores_none():
    monthly = [_pt(2022, 1, 10.0), _pt(2022, 2, None)]
    out = aggregate_by_granularity(monthly, "quarterly", **_STREAM_KW)
    assert out[0]["transmission_rate"] == 10.0  # None 제외 평균


def test_avg_all_none_is_none():
    monthly = [_pt(2022, 1, None), _pt(2022, 2, None)]
    out = aggregate_by_granularity(monthly, "quarterly", **_STREAM_KW)
    assert out[0]["transmission_rate"] is None


# ── yearly 집계 ───────────────────────────────────────────────────────────────

def test_yearly_groups_and_dec_period():
    monthly = [_pt(2021, 6, 5.0), _pt(2022, 1, 1.0), _pt(2022, 7, 3.0)]
    out = aggregate_by_granularity(monthly, "yearly", **_STREAM_KW)
    assert [p["period"] for p in out] == [date(2021, 12, 1), date(2022, 12, 1)]
    assert out[1]["transmission_rate"] == 2.0  # (1+3)/2


# ── raw_prices 필드 셋 (value/index_2020/has_anomaly) ─────────────────────────

def test_raw_field_set():
    monthly = [
        {"period": date(2022, 1, 1), "value": 100.0, "index_2020": 90.0,
         "has_anomaly": False, "anomaly_ids": []},
        {"period": date(2022, 2, 1), "value": 200.0, "index_2020": 110.0,
         "has_anomaly": True, "anomaly_ids": [7]},
    ]
    out = aggregate_by_granularity(
        monthly, "quarterly",
        avg_fields=("value", "index_2020"),
        any_fields=("has_anomaly",),
        concat_fields=("anomaly_ids",),
    )
    assert out[0]["value"] == 150.0
    assert out[0]["index_2020"] == 100.0
    assert out[0]["has_anomaly"] is True
    assert out[0]["anomaly_ids"] == [7]


# ── build_anomaly_density ─────────────────────────────────────────────────────

def test_build_anomaly_density_sums_by_year_sorted():
    rows = [
        SimpleNamespace(year=2022, high_count=1, medium_count=2, reference_count=3),
        SimpleNamespace(year=2021, high_count=10, medium_count=0, reference_count=0),
        SimpleNamespace(year=2022, high_count=4, medium_count=0, reference_count=1),
    ]
    out = build_anomaly_density(rows)
    assert [p.period for p in out] == ["2021", "2022"]  # 정렬
    assert out[1].high_count == 5       # 1+4 합산
    assert out[1].reference_count == 4  # 3+1


def test_build_anomaly_density_handles_null_counts():
    rows = [SimpleNamespace(year=2022, high_count=None, medium_count=None, reference_count=None)]
    out = build_anomaly_density(rows)
    assert out[0].high_count == 0
