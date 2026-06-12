"""APScheduler 월별 자동 배치 + 파이프라인 결과 DB 적재."""
from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.cache.redis import cache_delete_pattern, get_redis_client
from app.core.config import settings
from app.core.exceptions import DBError
from app.db.models.batch import DataFreshness, PipelineRun  # noqa: F401
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("app")

PHASES: list[str] = ["0", "1", "2", "3", "4", "5", "6", "7", "7-ml"]


def _call_pipeline(fn, *args, **kwargs):
    """파이프라인 함수 호출 — stdout을 StringIO로 흡수해 인코딩 오류 방지."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    captured = buf.getvalue()
    if captured.strip():
        logger.debug(
            "pipeline stdout captured",
            extra={"error_code": "BATCH", "context": {"output_preview": captured[:200]}},
        )
    return result


async def _run_phase(phase: str, run_id: int) -> None:
    """Phase 실행 — 파이프라인 계산 + DB 적재."""
    root = Path(settings.pipeline_data_root)

    logger.info(
        f"Phase {phase} 시작",
        extra={"error_code": "BATCH", "context": {"phase": phase, "run_id": run_id}},
    )

    loop = asyncio.get_event_loop()

    if phase == "0":
        from pipeline.preprocessing.run_phase0 import run_phase0
        await loop.run_in_executor(None, _call_pipeline, run_phase0)

    elif phase == "1":
        from pipeline.preprocessing.phase1_seasonal_adjustment import run_phase1
        merged_dir = str(root / "merged")
        config_path = str(root / "product_config.json")
        phase1_dir = str(root / "phase1")
        await loop.run_in_executor(
            None,
            _call_pipeline, run_phase1, merged_dir, config_path, phase1_dir,
        )

    elif phase == "2":
        from pipeline.preprocessing.phase2_stationarity_test import run_phase2
        from app.db.loader.phase2 import load_stationarity_results
        sa_dir = str(root / "phase1" / "seasonal_adjusted")
        config_path = str(root / "product_config.json")
        output_dir = str(root / "phase2")
        await loop.run_in_executor(
            None,
            _call_pipeline, run_phase2, sa_dir, config_path, output_dir,
        )
        async with AsyncSessionLocal() as session:
            await load_stationarity_results(session, run_id)

    elif phase == "3":
        from pipeline.preprocessing.phase3_cointegration_test import run_phase3
        from app.db.loader.phase3 import load_cointegration_results
        sa_dir = str(root / "phase1" / "seasonal_adjusted")
        config_path = str(root / "product_config.json")
        orders_path = str(root / "phase2" / "integration_orders.json")
        output_dir = str(root / "phase3")
        await loop.run_in_executor(
            None,
            _call_pipeline, run_phase3, sa_dir, config_path, orders_path, output_dir,
        )
        async with AsyncSessionLocal() as session:
            await load_cointegration_results(session, run_id)

    elif phase == "4":
        from pipeline.preprocessing.phase4_model_estimation import run_phase4
        from app.db.loader.phase4 import load_phase4
        sa_dir = str(root / "phase1" / "seasonal_adjusted")
        changes_dir = str(root / "phase1" / "changes")
        config_path = str(root / "product_config.json")
        routing_path = str(root / "phase3" / "model_routing.json")
        output_dir = str(root / "phase4")
        await loop.run_in_executor(
            None,
            _call_pipeline, run_phase4,
            sa_dir, changes_dir, config_path, routing_path, output_dir,
        )
        async with AsyncSessionLocal() as session:
            await load_phase4(session, run_id)

    elif phase == "5":
        from pipeline.preprocessing.phase5_granger_causality import run_phase5
        from app.db.loader.phase5 import load_granger_results
        await loop.run_in_executor(
            None,
            lambda: _call_pipeline(
                run_phase5,
                product_config_path=root / "product_config.json",
                model_routing_path=root / "phase3" / "model_routing.json",
                changes_dir=root / "phase1" / "changes",
                output_dir=root / "phase5",
            ),
        )
        async with AsyncSessionLocal() as session:
            await load_granger_results(session, run_id)

    elif phase == "6":
        from pipeline.preprocessing.phase6_structural_breaks import run_phase6
        from app.db.loader.phase6 import load_phase6
        await loop.run_in_executor(
            None,
            lambda: _call_pipeline(
                run_phase6,
                product_config_path=root / "product_config.json",
                model_routing_path=root / "phase3" / "model_routing.json",
                changes_dir=root / "phase1" / "changes",
                sa_dir=root / "phase1" / "seasonal_adjusted",
                phase4_dir=root / "phase4",
                output_dir=root / "phase6",
            ),
        )
        async with AsyncSessionLocal() as session:
            await load_phase6(session, run_id)

    elif phase == "7":
        from pipeline.preprocessing.Phase7.phase7_pattern1 import run_pattern1
        from pipeline.preprocessing.Phase7.phase7_pattern2 import run_pattern2
        from pipeline.preprocessing.Phase7.phase7_pattern3 import run_pattern3
        from pipeline.preprocessing.Phase7.phase7_integrate import run_integrate
        from app.db.loader.phase7 import load_phase7

        data_dir = str(root)
        output_dir = str(root / "phase7")
        await loop.run_in_executor(None, _call_pipeline, run_pattern1, data_dir, output_dir)
        await loop.run_in_executor(None, _call_pipeline, run_pattern2, data_dir, output_dir)
        await loop.run_in_executor(None, _call_pipeline, run_pattern3, data_dir, output_dir)
        await loop.run_in_executor(None, _call_pipeline, run_integrate, data_dir, output_dir)
        async with AsyncSessionLocal() as session:
            await load_phase7(session, run_id)

    elif phase == "7-ml":
        from pipeline.preprocessing.Phase7.phase7_ml_run import run_phase7_ml
        from app.db.loader.phase7_ml import load_phase7_ml

        data_dir = str(root)
        phase7_dir = str(root / "phase7")
        output_dir = str(root / "phase7_ml")
        await loop.run_in_executor(
            None, _call_pipeline, run_phase7_ml, data_dir, phase7_dir, output_dir,
        )
        async with AsyncSessionLocal() as session:
            await load_phase7_ml(session, run_id)

    else:
        logger.warning(
            f"알 수 없는 Phase {phase} — skip",
            extra={"error_code": "BATCH", "context": {"phase": phase, "run_id": run_id}},
        )


async def _prepare_run(
    run_date: date,
    data_up_to: date,
    next_run_date: date,
    started_at: datetime,
) -> tuple[int, dict]:
    """중복 체크 후 pipeline_runs UPSERT. (run_id, 초기 응답 dict) 반환."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PipelineRun).where(
                PipelineRun.run_date == run_date,
                PipelineRun.status == "running",
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.warning(
                "배치 중복 실행 감지 — 실행 skip (API-BATCH-002)",
                extra={
                    "error_code": "API-BATCH-002",
                    "context": {
                        "run_date": str(run_date),
                        "existing_run_id": existing.id,
                    },
                },
            )
            resp = {
                "run_id": existing.id,
                "status": "running",
                "run_date": str(run_date),
                "started_at": (
                    existing.started_at.isoformat()
                    if existing.started_at
                    else started_at.isoformat()
                ),
                "skipped": True,
            }
            return existing.id, resp

        stmt = (
            pg_insert(PipelineRun)
            .values(
                run_date=run_date,
                data_up_to=data_up_to,
                next_run_date=next_run_date,
                status="running",
                phases_run=[],
                started_at=started_at,
            )
            .on_conflict_do_update(
                index_elements=["run_date"],
                set_={
                    "status": "running",
                    "data_up_to": data_up_to,
                    "next_run_date": next_run_date,
                    "phases_run": [],
                    "error_message": None,
                    "started_at": started_at,
                    "finished_at": None,
                },
            )
            .returning(PipelineRun.id)
        )
        result = await db.execute(stmt)
        await db.commit()
        run_id: int = result.scalar_one()

    resp = {
        "run_id": run_id,
        "status": "running",
        "run_date": str(run_date),
        "started_at": started_at.isoformat(),
        "skipped": False,
    }
    return run_id, resp


async def _execute_phases(
    run_id: int,
    run_date: date,
    data_up_to: date,
    next_run_date: date,
) -> None:
    """Phase 0~7-ML 순차 호출 및 최종 status·data_freshness 갱신."""
    phases_run: list[str] = []
    error_message: Optional[str] = None
    status = "completed"

    try:
        for phase in PHASES:
            try:
                await _run_phase(phase, run_id)
                phases_run.append(phase)

                async with AsyncSessionLocal() as db:
                    await db.execute(
                        text(
                            "UPDATE pipeline_runs SET phases_run = :phases WHERE id = :id"
                        ),
                        {"phases": phases_run, "id": run_id},
                    )
                    await db.commit()

            except Exception as phase_err:
                error_message = f"Phase {phase} 실패: {phase_err!s}"
                raise DBError(
                    "DB-TX-001",
                    f"Phase {phase} 적재 중 예외 발생. ORM 세션 롤백.",
                    {
                        "phase": phase,
                        "run_id": run_id,
                        "underlying_error": str(phase_err),
                    },
                    table="pipeline_runs",
                ) from phase_err

    except Exception as exc:
        status = "failed"
        if error_message is None:
            error_message = str(exc)
        logger.error(
            "APScheduler 월별 배치 예외 — pipeline_runs.status='failed' 기록 (API-BATCH-001)",
            extra={
                "error_code": "API-BATCH-001",
                "context": {
                    "run_date": str(run_date),
                    "stage": "pipeline_execution",
                    "underlying_error": error_message,
                },
            },
        )

    finished_at = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                UPDATE pipeline_runs
                SET status        = :status,
                    phases_run    = :phases_run,
                    error_message = :error_message,
                    finished_at   = :finished_at
                WHERE id = :id
                """
            ),
            {
                "status": status,
                "phases_run": phases_run,
                "error_message": error_message,
                "finished_at": finished_at,
                "id": run_id,
            },
        )

        if status == "completed":
            upd = await db.execute(
                text(
                    """
                    UPDATE data_freshness
                    SET data_up_to      = :data_up_to,
                        next_run_date   = :next_run_date,
                        last_updated    = NOW(),
                        pipeline_run_id = :run_id
                    """
                ),
                {"data_up_to": data_up_to, "next_run_date": next_run_date, "run_id": run_id},
            )
            if upd.rowcount == 0:
                await db.execute(
                    text(
                        """
                        INSERT INTO data_freshness
                            (data_up_to, next_run_date, last_updated, pipeline_run_id)
                        VALUES (:data_up_to, :next_run_date, NOW(), :run_id)
                        """
                    ),
                    {
                        "data_up_to": data_up_to,
                        "next_run_date": next_run_date,
                        "run_id": run_id,
                    },
                )

        await db.commit()

    if status == "completed":
        await invalidate_cache(run_id)

    logger.info(
        f"배치 {status} 완료 — run_id={run_id}, run_date={run_date}",
        extra={"error_code": "BATCH", "context": {"run_id": run_id, "status": status}},
    )


def _calc_dates(run_date: date) -> tuple[date, date]:
    """배치 실행일 → data_up_to, next_run_date 계산."""
    # data_up_to: 전월 1일
    if run_date.month == 1:
        data_up_to = date(run_date.year - 1, 12, 1)
    else:
        data_up_to = date(run_date.year, run_date.month - 1, 1)

    next_month = run_date.month % 12 + 1
    next_year = run_date.year + (1 if run_date.month == 12 else 0)
    next_run_date = date(next_year, next_month, settings.batch_schedule_day)

    return data_up_to, next_run_date


async def start_batch(run_date: Optional[date] = None) -> dict:
    """pipeline_runs 초기 레코드 생성 후 run_id 반환 (트리거 엔드포인트용).

    # TODO: misfire 발생 시 직전 run_date 자동 보정 로직 추가 검토
    """
    if run_date is None:
        run_date = date.today()
    started_at = datetime.now(timezone.utc)
    data_up_to, next_run_date = _calc_dates(run_date)
    run_id, resp = await _prepare_run(run_date, data_up_to, next_run_date, started_at)
    return resp


async def run_monthly_pipeline(run_date: Optional[date] = None) -> None:
    """APScheduler cron 잡 진입점 — 초기화 + Phase 실행 일괄 처리."""
    if run_date is None:
        run_date = date.today()
    started_at = datetime.now(timezone.utc)
    data_up_to, next_run_date = _calc_dates(run_date)

    run_id, resp = await _prepare_run(run_date, data_up_to, next_run_date, started_at)
    if resp.get("skipped"):
        return

    await _execute_phases(run_id, run_date, data_up_to, next_run_date)


async def invalidate_cache(pipeline_run_id: int) -> None:
    """배치 완료 후 시계열 캐시 패턴 전체 삭제."""
    prefix = settings.redis_cache_prefix
    client = get_redis_client()
    patterns = [
        f"{prefix}:stream:*",
        f"{prefix}:raw-prices:*",
        f"{prefix}:stat-series:*",
    ]
    for pattern in patterns:
        count = await cache_delete_pattern(client, pattern)
        logger.info(
            f"캐시 무효화 완료 — pattern={pattern}, deleted={count}, run_id={pipeline_run_id}",
            extra={
                "error_code": "BATCH",
                "context": {
                    "pattern": pattern,
                    "deleted_count": count,
                    "pipeline_run_id": pipeline_run_id,
                },
            },
        )


def init_scheduler() -> AsyncIOScheduler:
    """APScheduler 인스턴스 생성 + 월별 cron 스케줄 등록."""
    sched = AsyncIOScheduler()
    sched.add_job(
        run_monthly_pipeline,
        CronTrigger(
            day=settings.batch_schedule_day,
            hour=settings.batch_schedule_hour,
            minute=0,
            timezone=settings.batch_schedule_tz,
        ),
        id="monthly_pipeline",
        name="월별 파이프라인 배치 (BE-BATCH)",
        misfire_grace_time=settings.batch_misfire_grace_sec,
        coalesce=True,
    )
    return sched
