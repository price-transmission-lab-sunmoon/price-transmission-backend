"""APScheduler 월별 자동 배치 + 파이프라인 결과 DB 적재 (feature_spec_BE-BATCH_v2)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.exceptions import DBError
from app.db.models.batch import DataFreshness, PipelineRun  # noqa: F401
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("app")

# Phase 실행 순서 (feature_spec_BE-BATCH_v2 §1.2)
PHASES: list[str] = ["0", "1", "2", "3", "4", "5", "6", "7", "7-ml"]


# ── Phase 실행 스텁 ────────────────────────────────────────────────────────────

async def _run_phase(phase: str, run_id: int) -> None:
    """Phase 실행 스텁.

    feat/be-db-pipeline dev 머지 + APP_ENV=production 전환 시 실제 파이프라인 호출로 교체.
    현재는 더미 모드 (feature_spec_BE-BATCH_v2 §6).
    """
    logger.info(
        f"Phase {phase} 실행 (더미 모드)",
        extra={"error_code": "BATCH", "context": {"phase": phase, "run_id": run_id}},
    )


# ── 배치 초기화 — run_id 확보 ─────────────────────────────────────────────────

async def _prepare_run(
    run_date: date,
    data_up_to: date,
    next_run_date: date,
    started_at: datetime,
) -> tuple[int, dict]:
    """중복 체크 후 pipeline_runs UPSERT, run_id 반환.

    Returns:
        (run_id, initial_response_dict)
        - API-BATCH-002: 동일 run_date에 status='running' 존재 시 기존 run_id 반환 + 로그
        - DB-RUN-001: UPSERT가 아닌 충돌 시 FATAL (현재 구조에선 on_conflict_do_update로 방지)
    """
    async with AsyncSessionLocal() as db:
        # API-BATCH-002: 동일 run_date 실행 중인 배치 확인
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

        # pipeline_runs UPSERT — status='running' 초기 기록 (db_schema_vN §D-17)
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


# ── Phase 순차 실행 + 최종 DB 기록 ────────────────────────────────────────────

async def _execute_phases(
    run_id: int,
    run_date: date,
    data_up_to: date,
    next_run_date: date,
) -> None:
    """Phase 0~7-ML 순차 호출 및 최종 status·data_freshness 갱신.

    API-BATCH-001: 임의 예외 발생 시 WARN 로그 + status='failed' 기록. 서버 유지.
    """
    phases_run: list[str] = []
    error_message: Optional[str] = None
    status = "completed"

    try:
        for phase in PHASES:
            try:
                await _run_phase(phase, run_id)
                phases_run.append(phase)

                # Phase 완료마다 phases_run 중간 갱신 (§3.1 트랜잭션 단위)
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
        # API-BATCH-001: WARN. 서버 유지. 다음 배치까지 대기.
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

    # 최종 상태 업데이트 — 예외 발생 시에도 반드시 기록 (API-BATCH-001 방침)
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

        # data_freshness 갱신 — status='completed' 시에만, 단독 트랜잭션 (§3.1)
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

    logger.info(
        f"배치 {status} 완료 — run_id={run_id}, run_date={run_date}",
        extra={"error_code": "BATCH", "context": {"run_id": run_id, "status": status}},
    )


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def _calc_dates(run_date: date) -> tuple[date, date]:
    """배치 실행일로부터 data_up_to, next_run_date 계산."""
    # data_up_to: 전월 1일 (db_schema_vN §설계원칙 6, DB-TYPE-001 방지)
    if run_date.month == 1:
        data_up_to = date(run_date.year - 1, 12, 1)
    else:
        data_up_to = date(run_date.year, run_date.month - 1, 1)

    # next_run_date: 다음달 batch_schedule_day일
    next_month = run_date.month % 12 + 1
    next_year = run_date.year + (1 if run_date.month == 12 else 0)
    next_run_date = date(next_year, next_month, settings.batch_schedule_day)

    return data_up_to, next_run_date


async def start_batch(run_date: Optional[date] = None) -> dict:
    """pipeline_runs 초기 레코드 생성 후 run_id 반환 (트리거 엔드포인트용).

    반환 dict에 'skipped': True 포함 시 API-BATCH-002 발동 (이미 실행 중).
    Phase 실행은 caller가 asyncio.create_task(_execute_phases(...))로 처리.
    """
    if run_date is None:
        run_date = date.today()
    started_at = datetime.now(timezone.utc)
    data_up_to, next_run_date = _calc_dates(run_date)
    run_id, resp = await _prepare_run(run_date, data_up_to, next_run_date, started_at)
    return resp


async def run_monthly_pipeline(run_date: Optional[date] = None) -> None:
    """APScheduler cron 잡 진입점 — 초기화 + Phase 실행 일괄 처리.

    배치 실패 시 서버 프로세스를 종료하지 않는다 (API-BATCH-001 방침).
    """
    if run_date is None:
        run_date = date.today()
    started_at = datetime.now(timezone.utc)
    data_up_to, next_run_date = _calc_dates(run_date)

    run_id, resp = await _prepare_run(run_date, data_up_to, next_run_date, started_at)
    if resp.get("skipped"):
        return  # API-BATCH-002: 이미 실행 중 → skip

    await _execute_phases(run_id, run_date, data_up_to, next_run_date)


# ── APScheduler 인스턴스 팩토리 ───────────────────────────────────────────────

def init_scheduler() -> AsyncIOScheduler:
    """APScheduler 인스턴스 생성 + 월별 cron 스케줄 등록.

    §4 파라미터 전체를 settings에서 참조 — 하드코딩 금지 (feature_spec_BE-BATCH_v2 §8).
    """
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
