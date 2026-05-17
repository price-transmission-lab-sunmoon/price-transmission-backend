"""Phase 2→3→4→5→6 순차 실행 진입점

feature_spec_DB-PIPELINE_v2 §3.3 pipeline_runs 기록 규칙.
exception_design_v3 §2 에러 체이닝 패턴 준수.

실행 순서:
  1. pipeline_runs INSERT (status='running')
  2. Phase 2: stationarity_results
  3. Phase 3: cointegration_results
  4. Phase 4: model_params, irf_data, baselines
  5. Phase 5: granger_results + cointegration_results.granger_direction UPDATE
  6. Phase 6: breakpoints, subperiods
  7. pipeline_runs UPDATE (status='completed')
  8. data_freshness UPSERT

실패 시: 해당 Phase 롤백 → pipeline_runs status='failed' → 이후 Phase 실행 중단.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DBError
from app.db.loader.base import (
    create_pipeline_run,
    update_pipeline_run_status,
    upsert_data_freshness,
)
from app.db.loader.phase2 import load_stationarity_results
from app.db.loader.phase3 import load_cointegration_results
from app.db.loader.phase4 import load_phase4
from app.db.loader.phase5 import load_granger_results
from app.db.loader.phase6 import load_phase6

logger = logging.getLogger(__name__)


async def run_pipeline(
    session: AsyncSession,
    run_date: date,
    data_up_to: date,
    next_run_date: date,
) -> dict:
    """Phase 2~6 전체 파이프라인 순차 실행.

    Args:
        session:       비동기 DB 세션
        run_date:      이번 배치 실행 날짜 (pipeline_runs.run_date UNIQUE 키)
        data_up_to:    데이터 기준 마지막 날짜 (data_freshness 갱신)
        next_run_date: 다음 예정 실행 날짜

    Returns:
        실행 결과 요약 dict
    """
    run_id = await create_pipeline_run(session, run_date, data_up_to)
    logger.info("파이프라인 시작", extra={"run_id": run_id, "run_date": str(run_date)})

    results: dict = {"run_id": run_id, "phases": {}}

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    try:
        rows = await load_stationarity_results(session, run_id)
        results["phases"]["2"] = {"stationarity_results": rows}
    except DBError as exc:
        await update_pipeline_run_status(session, run_id, "failed", error_message=str(exc))
        raise

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    try:
        rows = await load_cointegration_results(session, run_id)
        results["phases"]["3"] = {"cointegration_results": rows}
    except DBError as exc:
        await update_pipeline_run_status(session, run_id, "failed", error_message=str(exc))
        raise

    # ── Phase 4 ───────────────────────────────────────────────────────────────
    try:
        counts = await load_phase4(session, run_id)
        results["phases"]["4"] = counts
    except DBError as exc:
        await update_pipeline_run_status(session, run_id, "failed", error_message=str(exc))
        raise

    # ── Phase 5 ───────────────────────────────────────────────────────────────
    try:
        rows = await load_granger_results(session, run_id)
        results["phases"]["5"] = {"granger_results": rows}
    except DBError as exc:
        await update_pipeline_run_status(session, run_id, "failed", error_message=str(exc))
        raise

    # ── Phase 6 ───────────────────────────────────────────────────────────────
    try:
        counts = await load_phase6(session, run_id)
        results["phases"]["6"] = counts
    except DBError as exc:
        await update_pipeline_run_status(session, run_id, "failed", error_message=str(exc))
        raise

    # ── 완료 기록 ─────────────────────────────────────────────────────────────
    phases_run = [str(p) for p in sorted(results["phases"].keys(), key=int)]
    await update_pipeline_run_status(session, run_id, "completed", phases_run=phases_run)
    await upsert_data_freshness(session, run_id, data_up_to, next_run_date)

    logger.info(
        "파이프라인 완료",
        extra={"run_id": run_id, "phases_run": phases_run},
    )
    results["status"] = "completed"
    return results
