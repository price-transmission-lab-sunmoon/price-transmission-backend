"""Phase 6 — breakpoints / subperiods 적재.

JSON 필드명 매핑:
  segment → segment_id
  bai_perron_breakpoints → bp_dates DATE[]
  chow_test_points["2008/2020/2022-01"] → chow_*_f / _pvalue / _sig
  subperiods[].id/start/end/merged_with → subperiod_index / period_start / period_end / merged_with_index

bp_dates 파싱 실패 시 DB-ARR-002 WARN 후 NULL 적재.
bp_best_k / bic_scores 는 DB 미포함 → 적재 제외.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.loader.base import _v, append_phase_to_run, normalize_yyyymm_to_date, validate_period_day

logger = logging.getLogger(__name__)

_PHASE6_ROOT = Path(settings.pipeline_data_root) / "phase6"


def _parse_bp_dates(raw_list: list[str], cid: str, seg: str) -> list[date] | None:
    """'YYYY-MM' 배열 → DATE[] 월초 승격. 파싱 실패 시 WARN 후 None 반환."""
    if not raw_list:
        return []
    parsed: list[date] = []
    for raw in raw_list:
        try:
            d = normalize_yyyymm_to_date(str(raw))
            validate_period_day(d, "breakpoints.bp_dates")
            parsed.append(d)
        except Exception as exc:
            logger.warning(
                "DB-ARR-002 — bp_dates 파싱 실패, NULL 적재",
                extra={"commodity_id": cid, "segment_id": seg, "raw": raw, "error": str(exc)},
            )
            return None
    return parsed


def _chow(points: dict, key: str) -> tuple:
    pt = points.get(key, {})
    if not pt:
        return None, None, None
    return (
        _v(pt.get("f_stat")),
        _v(pt.get("pvalue")),
        _v(pt.get("significant")),
    )


async def load_phase6(
    session: AsyncSession,
    run_id: int,
) -> dict[str, int]:
    """Phase 6 단일 트랜잭션 — breakpoints, subperiods 적재."""
    bp_root = _PHASE6_ROOT / "breakpoints"
    files = sorted(bp_root.glob("*_breakpoints.json")) if bp_root.exists() else []

    bp_count = 0
    sp_count = 0

    try:
        for fp in files:
            data = json.loads(fp.read_text(encoding="utf-8"))

            cid = str(data["commodity_id"])
            seg = str(data.get("segment", data.get("segment_id", "")))

            raw_bp = data.get("bai_perron_breakpoints", [])
            bp_dates = _parse_bp_dates(raw_bp, cid, seg)

            chow_pts = data.get("chow_test_points", {})
            f2008, p2008, s2008 = _chow(chow_pts, "2008-01")
            f2020, p2020, s2020 = _chow(chow_pts, "2020-01")
            f2022, p2022, s2022 = _chow(chow_pts, "2022-01")

            await session.execute(
                text("""
                    INSERT INTO breakpoints (
                        commodity_id, segment_id, bp_dates,
                        chow_2008_f, chow_2008_pvalue, chow_2008_sig,
                        chow_2020_f, chow_2020_pvalue, chow_2020_sig,
                        chow_2022_f, chow_2022_pvalue, chow_2022_sig,
                        pipeline_run_id
                    ) VALUES (
                        :commodity_id, :segment_id, :bp_dates,
                        :chow_2008_f, :chow_2008_pvalue, :chow_2008_sig,
                        :chow_2020_f, :chow_2020_pvalue, :chow_2020_sig,
                        :chow_2022_f, :chow_2022_pvalue, :chow_2022_sig,
                        :pipeline_run_id
                    )
                    ON CONFLICT (commodity_id, segment_id) DO UPDATE SET
                        bp_dates = EXCLUDED.bp_dates,
                        chow_2008_f = EXCLUDED.chow_2008_f,
                        chow_2008_pvalue = EXCLUDED.chow_2008_pvalue,
                        chow_2008_sig = EXCLUDED.chow_2008_sig,
                        chow_2020_f = EXCLUDED.chow_2020_f,
                        chow_2020_pvalue = EXCLUDED.chow_2020_pvalue,
                        chow_2020_sig = EXCLUDED.chow_2020_sig,
                        chow_2022_f = EXCLUDED.chow_2022_f,
                        chow_2022_pvalue = EXCLUDED.chow_2022_pvalue,
                        chow_2022_sig = EXCLUDED.chow_2022_sig,
                        pipeline_run_id = EXCLUDED.pipeline_run_id
                """),
                {
                    "commodity_id": cid,
                    "segment_id": seg,
                    "bp_dates": bp_dates,
                    "chow_2008_f": f2008, "chow_2008_pvalue": p2008, "chow_2008_sig": s2008,
                    "chow_2020_f": f2020, "chow_2020_pvalue": p2020, "chow_2020_sig": s2020,
                    "chow_2022_f": f2022, "chow_2022_pvalue": p2022, "chow_2022_sig": s2022,
                    "pipeline_run_id": run_id,
                },
            )
            bp_count += 1

            for sp in data.get("subperiods", []):
                period_start = normalize_yyyymm_to_date(str(sp["start"]))
                period_end = normalize_yyyymm_to_date(str(sp["end"]))
                validate_period_day(period_start, "subperiods")
                validate_period_day(period_end, "subperiods")

                sp_index = int(sp["id"])
                merged_with = sp.get("merged_with")

                await session.execute(
                    text("""
                        INSERT INTO subperiods (
                            commodity_id, segment_id, subperiod_index,
                            period_start, period_end, n_obs, merged_with_index,
                            pipeline_run_id
                        ) VALUES (
                            :commodity_id, :segment_id, :subperiod_index,
                            :period_start, :period_end, :n_obs, :merged_with_index,
                            :pipeline_run_id
                        )
                        ON CONFLICT (commodity_id, segment_id, subperiod_index) DO UPDATE SET
                            period_start = EXCLUDED.period_start,
                            period_end = EXCLUDED.period_end,
                            n_obs = EXCLUDED.n_obs,
                            merged_with_index = EXCLUDED.merged_with_index,
                            pipeline_run_id = EXCLUDED.pipeline_run_id
                    """),
                    {
                        "commodity_id": cid,
                        "segment_id": seg,
                        "subperiod_index": sp_index,
                        "period_start": period_start,
                        "period_end": period_end,
                        "n_obs": int(sp["n_obs"]),
                        "merged_with_index": int(merged_with) if merged_with is not None else None,
                        "pipeline_run_id": run_id,
                    },
                )
                sp_count += 1

        await session.commit()
    except Exception as e:
        await session.rollback()
        if isinstance(e, DBError):
            raise
        raise DBError(
            "DB-TX-001",
            "Phase 6 트랜잭션 롤백 — breakpoints/subperiods 적재 실패",
            {"run_id": run_id, "error": str(e)},
        ) from e

    await append_phase_to_run(session, run_id, "6")
    logger.info(
        "Phase 6 완료",
        extra={"run_id": run_id, "breakpoints": bp_count, "subperiods": sp_count},
    )
    return {"breakpoints": bp_count, "subperiods": sp_count}
