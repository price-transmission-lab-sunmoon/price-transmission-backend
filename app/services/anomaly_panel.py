"""패널 엔드포인트 서비스 스텁 (실제 연동 단계: feat/phase7-stat 이후 구현 예정).

현재 모든 함수는 501 Not Implemented를 반환합니다.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError
from app.schemas.anomaly import AnomalyDetailResponse
from app.schemas.panel import (
    IRFResponse,
    MLMapResponse,
    StatSnapshotAsymmetryResponse,
    StatSnapshotIQRResponse,
)
from app.schemas.timeseries import StatSeriesResponse

_NOT_IMPLEMENTED = APIError(
    code="API-INT-NOT-IMPLEMENTED",
    message="패널 엔드포인트는 feat/phase7-stat 이후 구현 예정입니다.",
    http_status=501,
    public_code="NOT_IMPLEMENTED",
)


async def get_detail(anomaly_id: int, db: AsyncSession) -> AnomalyDetailResponse:
    raise _NOT_IMPLEMENTED


async def get_stat_series(
    anomaly_id: int,
    metric: str,
    from_: str | None,
    to: str | None,
    granularity: str,
    db: AsyncSession,
) -> StatSeriesResponse:
    raise _NOT_IMPLEMENTED


async def get_stat_snapshot_iqr(
    anomaly_id: int, db: AsyncSession
) -> StatSnapshotIQRResponse:
    raise _NOT_IMPLEMENTED


async def get_stat_snapshot_asymmetry(
    anomaly_id: int, db: AsyncSession
) -> StatSnapshotAsymmetryResponse:
    raise _NOT_IMPLEMENTED


async def get_irf(
    anomaly_id: int, include_subperiods: bool, db: AsyncSession
) -> IRFResponse:
    raise _NOT_IMPLEMENTED


async def get_ml_map(
    anomaly_id: int,
    model: str,
    projection_method: str,
    db: AsyncSession,
) -> MLMapResponse:
    raise _NOT_IMPLEMENTED
