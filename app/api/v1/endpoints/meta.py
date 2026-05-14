"""/meta/config, /meta/pipeline, /meta/analysis-params, /segments, /events, /freshness 엔드포인트 (api_spec_vN §방법론·설정 엔드포인트)."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.cache.redis import ping_redis
from app.core.config import settings
from app.schemas.meta import (
    MetaAnalysisParamsResponse,
    MetaConfigResponse,
    MetaPipelineResponse,
    PatternInfo,
    PipelineEdge,
    PipelineNode,
)
from app.services import reference as ref_svc

router = APIRouter()

_CACHE_CONTROL = "public, max-age=86400"


@router.get("/meta/config", response_model=MetaConfigResponse)
async def get_meta_config() -> MetaConfigResponse:
    """헬스체크 엔드포인트 — §8.2 frame 단계 신설."""
    from app.db.session import engine
    db_status: str
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "down"

    redis_ok = await ping_redis()

    return MetaConfigResponse(
        app_env=settings.app_env,
        db_status=db_status,
        redis_status="ok" if redis_ok else "down",
        frame_version=settings.frame_version,
    )


@router.get("/freshness")
async def get_freshness(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """데이터 기준 시점 — data_freshness 테이블 실 DB 조회."""
    response = await ref_svc.get_freshness(db)
    return JSONResponse(content=response.model_dump())


@router.get("/events")
async def get_events(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """외부 충격 이벤트 목록 — ETag + Cache-Control (api_spec_vN §GET /events)."""
    response, etag = await ref_svc.get_events(db)
    return JSONResponse(
        content=response.model_dump(),
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": _CACHE_CONTROL,
        },
    )


@router.get("/segments")
async def get_segments(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """분석 구간 정의 목록 — ETag + Cache-Control (api_spec_vN §GET /segments)."""
    response, etag = await ref_svc.get_segments(db)
    return JSONResponse(
        content=response.model_dump(),
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": _CACHE_CONTROL,
        },
    )


@router.get("/meta/pipeline", response_model=MetaPipelineResponse)
async def get_meta_pipeline() -> MetaPipelineResponse:
    """파이프라인 플로우 — 정적 데이터 (api_spec_vN §방법론 엔드포인트)."""
    return MetaPipelineResponse(
        version=settings.pipeline_spec_version,
        nodes=[
            PipelineNode(id="phase0", label="Phase 0", description="데이터 수집·전처리", phase_number=0),
            PipelineNode(id="phase1", label="Phase 1", description="계절 조정 (STL)", phase_number=1),
            PipelineNode(id="phase2", label="Phase 2", description="정상성 검정", phase_number=2),
            PipelineNode(id="phase3", label="Phase 3", description="공적분 검정", phase_number=3),
            PipelineNode(id="phase4_vecm", label="VECM 추정", description="장기 균형 포함 모형", phase_number=4),
            PipelineNode(id="phase4_var", label="VAR 추정", description="단기 동적 모형", phase_number=4),
            PipelineNode(id="phase5", label="Phase 5", description="Granger 인과 검정", phase_number=5),
            PipelineNode(id="phase6", label="Phase 6", description="구조 변화 탐지", phase_number=6),
            PipelineNode(id="phase7", label="Phase 7", description="통계 기반 이상 탐지", phase_number=7),
            PipelineNode(id="phase7_ml", label="Phase 7-ML", description="ML 보조 교차검증", phase_number=7.5),
            PipelineNode(id="phase8", label="Phase 8", description="결과 종합·등급화", phase_number=8),
        ],
        edges=[
            PipelineEdge(source="phase0", target="phase1"),
            PipelineEdge(source="phase1", target="phase2"),
            PipelineEdge(source="phase2", target="phase3"),
            PipelineEdge(source="phase3", target="phase4_vecm", label="공적분 있음"),
            PipelineEdge(source="phase3", target="phase4_var", label="공적분 없음"),
            PipelineEdge(source="phase4_vecm", target="phase5"),
            PipelineEdge(source="phase4_var", target="phase5"),
            PipelineEdge(source="phase5", target="phase6"),
            PipelineEdge(source="phase6", target="phase7"),
            PipelineEdge(source="phase6", target="phase7_ml"),
            PipelineEdge(source="phase7", target="phase8"),
            PipelineEdge(source="phase7_ml", target="phase8"),
        ],
    )


@router.get("/meta/analysis-params", response_model=MetaAnalysisParamsResponse)
async def get_meta_analysis_params() -> MetaAnalysisParamsResponse:
    """파이프라인 파라미터 기준값 — 정적 데이터."""
    return MetaAnalysisParamsResponse(
        version=settings.pipeline_spec_version,
        params={
            "rolling_window": 48,
            "zscore_warning": 2.0,
            "zscore_alert": 2.5,
            "iqr_multiplier": 1.5,
            "stability_threshold": 0.03,
            "pattern3_n_values": [2, 3, 6],
            "min_subperiod_obs": 60,
            "lag_search_range": [1, 4],
            "chow_test_points": ["2008-01", "2020-01", "2022-01"],
        },
        patterns=[
            PatternInfo(
                pattern_id="pattern1",
                label_kr="패턴 1: 방향 역전 및 시차 이탈",
                description="국제 원자재 가격이 변동할 때 다음 단계 가격이 반대 방향으로 움직이거나, 정상 전달 시차를 초과해도 하류가 무반응인 경우",
                applicable_segments=["A", "B", "C", "D", "D_prime"],
            ),
            PatternInfo(
                pattern_id="pattern2",
                label_kr="패턴 2: 전이율 크기 이탈 및 비대칭 전달(로켓-깃털 효과)",
                description="전이율이 롤링 Z-score와 IQR 기준을 동시 초과하거나, TECM/비대칭 VAR에서 상승·하락 조정 속도가 유의미하게 다른 경우",
                applicable_segments=["A", "B"],
            ),
            PatternInfo(
                pattern_id="pattern3",
                label_kr="패턴 3: 국제가격 안정기 중 하류 물가 스프레드 누적 확대",
                description="국제가 안정기에 수입단가-PPI 간 수준 괴리가 N개월 연속 같은 방향으로 확대되는 경우",
                applicable_segments=["B"],
            ),
        ],
    )
