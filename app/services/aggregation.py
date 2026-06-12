"""시계열 granularity 집계 + 연도별 이상 밀도 — stream/raw_prices 공통."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Literal

from app.schemas.timeseries import AnomalyDensityPoint


def quarter_key(d: date) -> tuple[int, int]:
    """(year, 0-indexed quarter)."""
    return (d.year, (d.month - 1) // 3)


def quarter_last_month(year: int, q0: int) -> date:
    """분기 마지막 월 1일 반환 (3·6·9·12월)."""
    return date(year, (q0 + 1) * 3, 1)


def _group_key(p: dict, granularity: str):
    if granularity == "quarterly":
        return quarter_key(p["period"])
    return p["period"].year  # yearly


def _group_period(k, granularity: str) -> date:
    if granularity == "quarterly":
        return quarter_last_month(k[0], k[1])
    return date(k, 12, 1)  # yearly


def aggregate_by_granularity(
    monthly: list[dict],
    granularity: Literal["monthly", "quarterly", "yearly"],
    *,
    avg_fields: Sequence[str],
    any_fields: Sequence[str] = (),
    concat_fields: Sequence[str] = (),
) -> list[dict]:
    """월 단위 포인트를 granularity로 집계.

    avg_fields: None 제외 평균, any_fields: 하나라도 True 면 True,
    concat_fields: 리스트 평탄화 결합. monthly 이면 원본 그대로 반환.
    """
    if granularity == "monthly":
        return monthly

    groups: dict = defaultdict(list)
    for p in monthly:
        groups[_group_key(p, granularity)].append(p)

    result: list[dict] = []
    for k in sorted(groups):
        grp = groups[k]
        row: dict = {"period": _group_period(k, granularity)}
        for f in avg_fields:
            vals = [p[f] for p in grp if p[f] is not None]
            row[f] = sum(vals) / len(vals) if vals else None
        for f in any_fields:
            row[f] = any(p[f] for p in grp)
        for f in concat_fields:
            row[f] = [x for p in grp for x in p[f]]
        result.append(row)
    return result


def build_anomaly_density(density_rows) -> list[AnomalyDensityPoint]:
    """mv_anomaly_density_yearly 행 → 연도별 구간 합산 목록."""
    year_density: dict[int, dict] = {}
    for dr in density_rows:
        y = int(dr.year)
        bucket = year_density.setdefault(
            y, {"high_count": 0, "medium_count": 0, "reference_count": 0}
        )
        bucket["high_count"] += int(dr.high_count or 0)
        bucket["medium_count"] += int(dr.medium_count or 0)
        bucket["reference_count"] += int(dr.reference_count or 0)

    return [
        AnomalyDensityPoint(
            period=str(y),
            high_count=v["high_count"],
            medium_count=v["medium_count"],
            reference_count=v["reference_count"],
        )
        for y, v in sorted(year_density.items())
    ]
