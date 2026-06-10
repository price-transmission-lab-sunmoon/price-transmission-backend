"""DB-PIPELINE 적재 로직 단위/통합 테스트 — feature_spec_DB-PIPELINE_v2 §7 완료 기준 검증.

테스트 전략:
- Phase 2~3: 샘플 CSV 픽스처 경유, AsyncMock 세션으로 UPSERT SQL 호출 확인
- 타입 변환: DB-TYPE-001 FATAL (period.day != 1), DB-ARR-002 WARN (bp_dates 파싱 실패)
- 트랜잭션 롤백: Phase 적재 중 예외 발생 시 rollback + DB-TX-001 재발생 확인
- pipeline_runs: create/update/append 기본 호출 확인
- runner: Phase 실패 시 status='failed' 기록 후 즉시 중단

실 DB 없이 실행 가능하도록 AsyncMock 세션 사용.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.exceptions import DBError
from app.db.loader.base import _v, normalize_yyyymm_to_date, validate_period_day

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pipeline"


# ── _v() 헬퍼 ─────────────────────────────────────────────────────────────────

def test_v_none():
    assert _v(None) is None


def test_v_nan():
    import math
    assert _v(float("nan")) is None


def test_v_string():
    assert _v("stationary") == "stationary"


def test_v_bool():
    assert _v(True) is True


def test_v_zero():
    assert _v(0) == 0


# ── normalize_yyyymm_to_date ──────────────────────────────────────────────────

def test_normalize_yyyymm_ok():
    d = normalize_yyyymm_to_date("2022-03")
    assert d == date(2022, 3, 1)


def test_normalize_yyyymm_invalid():
    with pytest.raises(DBError) as exc_info:
        normalize_yyyymm_to_date("2022-13")
    assert exc_info.value.code == "DB-TYPE-001"


def test_normalize_yyyymm_bad_format():
    with pytest.raises(DBError) as exc_info:
        normalize_yyyymm_to_date("20220301")
    assert exc_info.value.code == "DB-TYPE-001"


# ── validate_period_day (D-11) ────────────────────────────────────────────────

def test_validate_period_day_ok():
    validate_period_day(date(2022, 3, 1), "test_table")  # 예외 없음


def test_validate_period_day_fail():
    with pytest.raises(DBError) as exc_info:
        validate_period_day(date(2022, 3, 15), "test_table")
    assert exc_info.value.code == "DB-TYPE-001"


# ── Phase 2 — load_stationarity_results ──────────────────────────────────────

@pytest.mark.asyncio
async def test_phase2_loads_csv(tmp_path):
    """샘플 CSV 경유 UPSERT SQL 실행 확인."""
    # 픽스처 CSV를 tmp_path 에 복사하여 pipeline_data_root 로 사용
    phase2_dir = tmp_path / "phase2"
    phase2_dir.mkdir()
    src = _FIXTURE_DIR / "phase2_sample.csv"
    (phase2_dir / "stationarity_results.csv").write_bytes(src.read_bytes())

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    with patch("app.db.loader.phase2.settings") as mock_settings, \
         patch("app.db.loader.phase2.append_phase_to_run", new_callable=AsyncMock) as mock_append:
        mock_settings.pipeline_data_root = str(tmp_path)
        from app.db.loader.phase2 import load_stationarity_results
        count = await load_stationarity_results(session, run_id=1)

    assert count == 9  # phase2_sample.csv 행 수
    assert session.execute.call_count == 9
    assert session.commit.called
    mock_append.assert_awaited_once_with(session, 1, "2")


@pytest.mark.asyncio
async def test_phase2_file_not_found():
    """파일 미존재 시 DB-TX-001 발생."""
    session = AsyncMock()
    with patch("app.db.loader.phase2.settings") as mock_settings:
        mock_settings.pipeline_data_root = "/nonexistent/path"
        from app.db.loader.phase2 import load_stationarity_results
        with pytest.raises(DBError) as exc_info:
            await load_stationarity_results(session, run_id=1)
    assert exc_info.value.code == "DB-TX-001"


@pytest.mark.asyncio
async def test_phase2_rollback_on_db_error(tmp_path):
    """DB execute 실패 시 rollback 후 DB-TX-001 재발생."""
    phase2_dir = tmp_path / "phase2"
    phase2_dir.mkdir()
    src = _FIXTURE_DIR / "phase2_sample.csv"
    (phase2_dir / "stationarity_results.csv").write_bytes(src.read_bytes())

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=Exception("DB connection lost"))
    session.rollback = AsyncMock()

    with patch("app.db.loader.phase2.settings") as mock_settings:
        mock_settings.pipeline_data_root = str(tmp_path)
        from app.db.loader.phase2 import load_stationarity_results
        with pytest.raises(DBError) as exc_info:
            await load_stationarity_results(session, run_id=1)

    assert exc_info.value.code == "DB-TX-001"
    session.rollback.assert_awaited()


# ── Phase 6 — bp_dates 파싱 (DB-ARR-002 WARN) ────────────────────────────────

def test_phase6_bp_dates_parse_ok():
    from app.db.loader.phase6 import _parse_bp_dates
    result = _parse_bp_dates(["2013-05", "2020-11"], "wheat", "D_prime")
    assert result == [date(2013, 5, 1), date(2020, 11, 1)]


def test_phase6_bp_dates_parse_warn_on_failure():
    """형식 불일치 시 DB-ARR-002 WARN → None 반환 (FATAL 아님)."""
    from app.db.loader.phase6 import _parse_bp_dates
    result = _parse_bp_dates(["invalid-date"], "wheat", "D_prime")
    assert result is None  # WARN 후 NULL 적재


def test_phase6_bp_dates_empty():
    from app.db.loader.phase6 import _parse_bp_dates
    result = _parse_bp_dates([], "wheat", "A")
    assert result == []


# ── DB-TYPE-001: period.day != 1 주입 ────────────────────────────────────────

def test_period_day_not_1_is_fatal():
    """period.day != 1 주입 시 DB-TYPE-001 FATAL (§7 완료 기준)."""
    with pytest.raises(DBError) as exc_info:
        validate_period_day(date(2026, 3, 15), "stationarity_results")
    assert exc_info.value.code == "DB-TYPE-001"
    assert "월초" in exc_info.value.message


# ── runner.py — Phase 실패 시 status='failed' ──────────────────────────────

@pytest.mark.asyncio
async def test_runner_marks_failed_on_phase2_error():
    """Phase 2 실패 시 pipeline_runs.status='failed' 기록 후 즉시 종료."""
    session = AsyncMock()

    with patch("app.db.loader.runner.create_pipeline_run", new_callable=AsyncMock, return_value=42) as mock_create, \
         patch("app.db.loader.runner.load_stationarity_results", new_callable=AsyncMock,
               side_effect=DBError("DB-TX-001", "Phase 2 실패", {})) as mock_p2, \
         patch("app.db.loader.runner.update_pipeline_run_status", new_callable=AsyncMock) as mock_update, \
         patch("app.db.loader.runner.load_cointegration_results", new_callable=AsyncMock) as mock_p3:

        from app.db.loader.runner import run_pipeline
        with pytest.raises(DBError):
            await run_pipeline(
                session,
                run_date=date(2026, 5, 17),
                data_up_to=date(2026, 4, 1),
                next_run_date=date(2026, 6, 15),
            )

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args
    assert call_kwargs[0][2] == "failed"   # 3rd positional arg: status
    mock_p3.assert_not_awaited()           # Phase 3 실행 중단 확인
