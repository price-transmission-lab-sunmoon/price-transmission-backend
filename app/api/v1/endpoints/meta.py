"""/meta/config, /meta/pipeline, /meta/analysis-params, /segments, /events, /freshness 엔드포인트 (api_spec_vN §방법론·설정 엔드포인트)."""
from fastapi import APIRouter, Request, Response

from app.cache.redis import ping_redis
from app.core.config import settings
from app.schemas.commodity import SegmentItem, SegmentListResponse
from app.schemas.meta import (
    EventItem,
    EventListResponse,
    FreshnessResponse,
    MetaAnalysisParamsResponse,
    MetaConfigResponse,
    MetaPipelineResponse,
)
from app.services.meta import build_analysis_params_response, build_pipeline_response

router = APIRouter()


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


@router.get("/freshness", response_model=FreshnessResponse)
async def get_freshness() -> FreshnessResponse:
    """데이터 기준 시점 — 더미 응답 (§8.1)."""
    return FreshnessResponse(
        data_up_to="2026-03",
        next_run_date="2026-04-15",
        last_updated="2026-04-01T03:00:00Z",
    )


@router.get("/events", response_model=EventListResponse)
async def get_events() -> EventListResponse:
    """외부 충격 이벤트 목록 — db_schema_vN §external_events 초기 데이터."""
    return EventListResponse(
        events=[
            EventItem(event_key="financial_crisis_2008", label_kr="2008 금융위기", start_date="2008-07", end_date="2009-03", color_hex="#F97316"),
            EventItem(event_key="covid19_2020", label_kr="2020 코로나19", start_date="2020-02", end_date="2021-06", color_hex="#22C55E"),
            EventItem(event_key="brazil_frost_2021", label_kr="2021~22 브라질 서리", start_date="2021-07", end_date="2022-03", color_hex="#38BDF8"),
            EventItem(event_key="ukraine_2022", label_kr="2022 우크라이나 사태", start_date="2022-02", end_date="2022-10", color_hex="#EF4444"),
            EventItem(event_key="indonesia_palmoil_2022", label_kr="2022 인도네시아 팜유 수출 규제", start_date="2022-04", end_date="2022-05", color_hex="#FB923C"),
        ]
    )


@router.get("/segments", response_model=SegmentListResponse)
async def get_segments() -> SegmentListResponse:
    """분석 구간 정의 목록 — db_schema_vN §segments 초기 데이터."""
    return SegmentListResponse(
        segments=[
            SegmentItem(segment_id="A", label_kr="구간 A (국제가→수입단가)", upstream_label="국제가 (원화 환산)", downstream_label="수입단가", applies_to="all", pattern1=True, pattern2=True, pattern3=False, ml_applied=True),
            SegmentItem(segment_id="B", label_kr="구간 B (수입단가→PPI)", upstream_label="수입단가", downstream_label="PPI", applies_to="all", pattern1=True, pattern2=True, pattern3=True, ml_applied=True),
            SegmentItem(segment_id="C", label_kr="구간 C (PPI→도매가)", upstream_label="PPI", downstream_label="도매가", applies_to="4seg", pattern1=True, pattern2=False, pattern3=False, ml_applied=False),
            SegmentItem(segment_id="D", label_kr="구간 D (도매가→CPI)", upstream_label="도매가", downstream_label="CPI", applies_to="4seg", pattern1=True, pattern2=False, pattern3=False, ml_applied=False),
            SegmentItem(segment_id="D_prime", label_kr="구간 D′ (PPI→CPI)", upstream_label="PPI", downstream_label="CPI", applies_to="3seg", pattern1=True, pattern2=False, pattern3=False, ml_applied=False),
        ]
    )


@router.get("/meta/pipeline", response_model=MetaPipelineResponse)
async def get_meta_pipeline(request: Request, response: Response) -> MetaPipelineResponse:
    """파이프라인 플로우 — 정적 데이터 + ETag (api_spec_v5 §방법론 엔드포인트).

    노드 11개, 엣지 12개. ETag + Cache-Control: max-age=86400 포함.
    If-None-Match 일치 시 304 Not Modified 반환.
    """
    data, etag = build_pipeline_response()
    etag_header = f'"{etag}"'
    response.headers["ETag"] = etag_header
    response.headers["Cache-Control"] = "max-age=86400"

    if request.headers.get("if-none-match") == etag_header:
        return Response(
            status_code=304,
            headers={"ETag": etag_header, "Cache-Control": "max-age=86400"},
        )

    return data


@router.get("/meta/analysis-params", response_model=MetaAnalysisParamsResponse)
async def get_meta_analysis_params(request: Request, response: Response) -> MetaAnalysisParamsResponse:
    """파라미터 기준값 — 정적 데이터 + ETag (api_spec_v5 §방법론 엔드포인트).

    settings.py 등록 키(ROLLING_WINDOW, ZSCORE_WARNING, ZSCORE_ALERT) 참조.
    신규 키(IQR_MULTIPLIER 등)는 services/meta.py _DEFAULTS 참조 (PM 승인 전).
    If-None-Match 일치 시 304 Not Modified 반환.
    """
    data, etag = build_analysis_params_response()
    etag_header = f'"{etag}"'
    response.headers["ETag"] = etag_header
    response.headers["Cache-Control"] = "max-age=86400"

    if request.headers.get("if-none-match") == etag_header:
        return Response(
            status_code=304,
            headers={"ETag": etag_header, "Cache-Control": "max-age=86400"},
        )

    return data
