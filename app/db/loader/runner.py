"""Phase 2에서 7-ML까지 순차 실행 진입점.

실패 시 해당 Phase를 롤백하고 pipeline_runs status를 'failed'로 갱신하며 이후 Phase를 중단한다.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DBError
from app.db.loader.base import (
    append_phase_to_run,
    create_pipeline_run,
    update_pipeline_run_status,
    upsert_data_freshness,
)
from app.db.loader.phase2 import load_stationarity_results
from app.db.loader.phase3 import load_cointegration_results
from app.db.loader.phase4 import load_phase4
from app.db.loader.phase5 import load_granger_results
from app.db.loader.phase6 import load_phase6
from app.db.loader.phase7 import load_phase7
from app.db.loader.phase7_ml import load_phase7_ml

logger = logging.getLogger(__name__)


async def run_pipeline(
    session: AsyncSession,
    run_date: date,
    data_up_to: date,
    next_run_date: date,
) -> dict:
    """Phase 2~7-ml 전체 파이프라인 순차 실행. 결과 요약 dict 반환."""
    # TODO: 실패 Phase 번호를 인자로 받아 해당 지점부터 재시작하는 기능 추가 검토
    run_id = await create_pipeline_run(session, run_date, data_up_to)
    logger.info("파이프라인 시작", extra={"run_id": run_id, "run_date": str(run_date)})

    results: dict = {"run_id": run_id, "phases": {}}

    def _phase_order_key(p: str) -> tuple[int, int]:
        # '7-ml'은 (7, 1)로 Phase 7 직후에 오도록 정렬
        if "-" in p:
            base, _ = p.split("-", 1)
            return (int(base), 1)
        return (int(p), 0)

    def _completed_phases() -> list[str]:
        return [str(p) for p in sorted(results["phases"].keys(), key=_phase_order_key)]

    try:
        rows = await load_stationarity_results(session, run_id)
        results["phases"]["2"] = {"stationarity_results": rows}
        await append_phase_to_run(session, run_id, "2")
    except DBError as exc:
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=str(exc),
        )
        raise

    try:
        rows = await load_cointegration_results(session, run_id)
        results["phases"]["3"] = {"cointegration_results": rows}
        await append_phase_to_run(session, run_id, "3")
    except DBError as exc:
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=str(exc),
        )
        raise

    try:
        counts = await load_phase4(session, run_id)
        results["phases"]["4"] = counts
        await append_phase_to_run(session, run_id, "4")
    except DBError as exc:
        error_msg = str(exc)
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=error_msg,
        )
        raise

    try:
        rows = await load_granger_results(session, run_id)
        results["phases"]["5"] = {"granger_results": rows}
        await append_phase_to_run(session, run_id, "5")
    except DBError as exc:
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=str(exc),
        )
        raise

    try:
        counts = await load_phase6(session, run_id)
        results["phases"]["6"] = counts
        await append_phase_to_run(session, run_id, "6")
    except DBError as exc:
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=str(exc),
        )
        raise

    try:
        counts = await load_phase7(session, run_id)
        results["phases"]["7"] = counts
    except DBError as exc:
        error_msg = str(exc)
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=error_msg,
        )
        raise

    try:
        counts = await load_phase7_ml(session, run_id)
        results["phases"]["7-ml"] = counts
    except DBError as exc:
        await update_pipeline_run_status(
            session, run_id, "failed",
            phases_run=_completed_phases() or None,
            error_message=str(exc),
        )
        raise

    phases_run = _completed_phases()
    await update_pipeline_run_status(session, run_id, "completed", phases_run=phases_run)
    await upsert_data_freshness(session, run_id, data_up_to, next_run_date)

    logger.info(
        "파이프라인 완료",
        extra={"run_id": run_id, "phases_run": phases_run},
    )
    results["status"] = "completed"
    return results
