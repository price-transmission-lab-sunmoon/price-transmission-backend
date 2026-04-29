"""APIRouter 통합 — prefix='/api/v1' (api_spec_v4 §공통 사항)."""
from fastapi import APIRouter

from app.api.v1.endpoints import anomalies, commodities, meta

router = APIRouter(prefix="/api/v1")

router.include_router(meta.router, tags=["meta"])
router.include_router(commodities.router, tags=["commodities"])
router.include_router(anomalies.router, tags=["anomalies"])
