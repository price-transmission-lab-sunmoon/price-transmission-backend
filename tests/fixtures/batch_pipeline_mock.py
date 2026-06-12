"""배치 파이프라인 더미 픽스처 — 배치 흐름만 테스트하기 위한 Phase 실행 대체."""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

logger = logging.getLogger("app")

DUMMY_PHASES = ["0", "1", "2", "3", "4", "5", "6", "7", "7-ml"]


async def dummy_run_phase(phase: str, run_id: int) -> None:
    logger.info(
        f"[MOCK] Phase {phase} 더미 실행",
        extra={"error_code": "BATCH_MOCK", "context": {"phase": phase, "run_id": run_id}},
    )


def dummy_run_phase_fail_at(fail_phase: str):
    """특정 Phase에서 의도적으로 실패하는 더미 팩토리."""
    async def _phase_runner(phase: str, run_id: int) -> None:
        if phase == fail_phase:
            raise RuntimeError(f"의도적 Phase {phase} 실패 (테스트용)")
        await dummy_run_phase(phase, run_id)
    return _phase_runner


@pytest.fixture()
def mock_batch_phases():
    with patch("app.services.batch._run_phase", side_effect=dummy_run_phase):
        yield


@pytest.fixture()
def mock_batch_phases_fail_at_phase7():
    """Phase 7에서 의도적 실패 유발 fixture."""
    with patch("app.services.batch._run_phase", side_effect=dummy_run_phase_fail_at("7")):
        yield
