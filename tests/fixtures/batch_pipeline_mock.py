"""배치 파이프라인 더미 픽스처 (feature_spec_BE-BATCH_v2 §6).

실제 feat/pipeline-* 산출물 대신 더미 함수로 대체하여 배치 흐름만 테스트한다.
APP_ENV=development + 이 픽스처로 로컬 실행 시 배치 전체 흐름(API-BATCH-001/002 포함)을
실제 파이프라인 호출 없이 검증할 수 있다.

더미 → 실제 전환 트리거:
  feat/be-db-pipeline dev 머지 완료 후, APP_ENV=production 전환 시 실제 파이프라인 호출로 교체.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

logger = logging.getLogger("app")

DUMMY_PHASES = ["0", "1", "2", "3", "4", "5", "6", "7", "7-ml"]


async def dummy_run_phase(phase: str, run_id: int) -> None:
    """Phase 실행 더미 — 즉시 성공 반환."""
    logger.info(
        f"[MOCK] Phase {phase} 더미 실행",
        extra={"error_code": "BATCH_MOCK", "context": {"phase": phase, "run_id": run_id}},
    )


async def dummy_run_phase_fail_at(fail_phase: str):
    """특정 Phase에서 의도적으로 실패하는 더미 팩토리 (실패 시나리오 테스트용)."""
    async def _phase_runner(phase: str, run_id: int) -> None:
        if phase == fail_phase:
            raise RuntimeError(f"의도적 Phase {phase} 실패 (테스트용)")
        await dummy_run_phase(phase, run_id)
    return _phase_runner


@pytest.fixture()
def mock_batch_phases():
    """모든 Phase를 더미로 교체하는 pytest fixture."""
    with patch("app.services.batch._run_phase", side_effect=dummy_run_phase):
        yield


@pytest.fixture()
def mock_batch_phases_fail_at_phase7():
    """Phase 7에서 의도적 실패 유발 fixture (API-BATCH-001 시나리오)."""
    fail_runner = None

    async def _setup():
        nonlocal fail_runner
        fail_runner = await dummy_run_phase_fail_at("7")
        return fail_runner

    import asyncio
    fail_runner = asyncio.get_event_loop().run_until_complete(_setup())

    with patch("app.services.batch._run_phase", side_effect=fail_runner):
        yield
