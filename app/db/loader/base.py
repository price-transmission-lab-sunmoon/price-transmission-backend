"""pipeline_runs 기록 + 트랜잭션 공통 유틸리티

feature_spec_DB-PIPELINE_v2 §3.3, §5.1 기준.
exception_design_v3 §2 에러 체이닝 패턴 준수.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DBError

logger = logging.getLogger(__name__)


# ── 공통 유틸리티 ────────────────────────────────────────────────────────────

def _v(val):
    """pandas NaN / None → Python None, 그 외 원형 반환."""
    if val is None:
        return None
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


# ── 날짜 유틸리티 ────────────────────────────────────────────────────────────

def normalize_yyyymm_to_date(raw: str) -> date:
    """'YYYY-MM' 문자열 → date(YYYY, MM, 1).

    D-11: period.day == 1 검증. 실패 시 DB-TYPE-001 FATAL.
    """
    try:
        parts = raw.strip().split("-")
        if len(parts) != 2:
            raise ValueError(f"형식 불일치: {raw!r}")
        year, month = int(parts[0]), int(parts[1])
        return date(year, month, 1)
    except Exception as e:
        raise DBError(
            "DB-TYPE-001",
            f"period 변환 실패 — 월초(YYYY-MM-01) 아님: {raw!r}",
            {"period_raw": raw},
        ) from e


def validate_period_day(d: date, table: str) -> None:
    """period.day == 1 검증 (D-11). 실패 시 DB-TYPE-001 FATAL."""
    if d.day != 1:
        raise DBError(
            "DB-TYPE-001",
            f"period가 월초가 아님 (D-11): {d}",
            {"table": table, "period_raw": str(d)},
        )


# ── pipeline_runs CRUD ───────────────────────────────────────────────────────

async def create_pipeline_run(
    session: AsyncSession,
    run_date: date,
    data_up_to: date,
) -> int:
    """pipeline_runs 에 'running' 상태로 1건 INSERT. run_id 반환.

    중복 run_date 시 DB-RUN-001 FATAL.
    """
    try:
        result = await session.execute(
            text(
                """
                INSERT INTO pipeline_runs (run_date, data_up_to, status, started_at)
                VALUES (:run_date, :data_up_to, 'running', now())
                RETURNING id
                """
            ),
            {"run_date": run_date, "data_up_to": data_up_to},
        )
        await session.commit()
        run_id: int = result.scalar_one()
        logger.info("pipeline_runs 생성", extra={"run_id": run_id, "run_date": str(run_date)})
        return run_id
    except IntegrityError as e:
        await session.rollback()
        raise DBError(
            "DB-RUN-001",
            f"pipeline_runs 중복 생성 — run_date={run_date} 이미 존재",
            {"run_date": str(run_date)},
        ) from e


async def update_pipeline_run_status(
    session: AsyncSession,
    run_id: int,
    status: Literal["completed", "failed"],
    phases_run: list[str] | None = None,
    error_message: str | None = None,
) -> None:
    """pipeline_runs.status 갱신 + finished_at 기록."""
    await session.execute(
        text(
            """
            UPDATE pipeline_runs
            SET status = :status,
                phases_run = :phases_run,
                error_message = :error_message,
                finished_at = now()
            WHERE id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "phases_run": phases_run,
            "error_message": error_message,
        },
    )
    await session.commit()
    logger.info(
        "pipeline_runs 상태 갱신",
        extra={"run_id": run_id, "status": status, "phases_run": phases_run},
    )


async def append_phase_to_run(
    session: AsyncSession,
    run_id: int,
    phase: str,
) -> None:
    """phases_run 배열에 완료 Phase 번호를 누적 추가."""
    await session.execute(
        text(
            """
            UPDATE pipeline_runs
            SET phases_run = array_append(coalesce(phases_run, '{}'), :phase)
            WHERE id = :run_id
            """
        ),
        {"run_id": run_id, "phase": phase},
    )
    await session.commit()


async def upsert_data_freshness(
    session: AsyncSession,
    run_id: int,
    data_up_to: date,
    next_run_date: date,
) -> None:
    """data_freshness 테이블 — 항상 최신 1개 행 유지 UPSERT.

    feature_spec_DB-PIPELINE_v2 §3.2: Phase 전체 완료 후 갱신.
    """
    await session.execute(
        text(
            """
            INSERT INTO data_freshness (data_up_to, next_run_date, last_updated, pipeline_run_id)
            VALUES (:data_up_to, :next_run_date, now(), :run_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"data_up_to": data_up_to, "next_run_date": next_run_date, "run_id": run_id},
    )
    # 기존 행이 있으면 UPDATE
    await session.execute(
        text(
            """
            UPDATE data_freshness
            SET data_up_to = :data_up_to,
                next_run_date = :next_run_date,
                last_updated = now(),
                pipeline_run_id = :run_id
            WHERE id = (SELECT id FROM data_freshness ORDER BY id LIMIT 1)
            """
        ),
        {"data_up_to": data_up_to, "next_run_date": next_run_date, "run_id": run_id},
    )
    await session.commit()
