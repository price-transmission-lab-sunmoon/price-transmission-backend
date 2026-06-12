"""정적 메타 데이터 응답 생성 + ETag 계산.

DB 세션 의존성 없음. 정적 딕셔너리 + settings.py 파라미터만 사용.
"""
import hashlib
import json

from app.core.config import settings
from app.schemas.meta import (
    AnalysisParams,
    MetaAnalysisParamsResponse,
    MetaPipelineResponse,
    PatternInfo,
    PipelineEdge,
    PipelineNode,
)

# TODO: settings.py로 이전 검토 (_DEFAULTS 키들을 settings 환경변수로 관리)
_DEFAULTS: dict = {
    "pipeline_version": "v8",          # → PIPELINE_VERSION
    "iqr_multiplier": 1.5,             # → IQR_MULTIPLIER
    "stability_threshold": 0.03,       # → STABILITY_THRESHOLD
    "pattern3_n_values": [2, 3, 6],    # → PATTERN3_N_VALUES
    "min_subperiod_obs": 60,           # → MIN_SUBPERIOD_OBS
    "lag_search_range": [1, 4],        # → LAG_SEARCH_RANGE
    "chow_test_points": ["2008-01", "2020-01", "2022-01"],  # → CHOW_TEST_POINTS
}

_PIPELINE_NODES: list[PipelineNode] = [
    PipelineNode(id="phase0",      label="Phase 0",    description="데이터 수집·전처리",  phase_number=0),
    PipelineNode(id="phase1",      label="Phase 1",    description="계절 조정 (STL)",     phase_number=1),
    PipelineNode(id="phase2",      label="Phase 2",    description="정상성 검정",          phase_number=2),
    PipelineNode(id="phase3",      label="Phase 3",    description="공적분 검정",          phase_number=3),
    PipelineNode(id="phase4_vecm", label="VECM 추정",  description="장기 균형 포함 모형", phase_number=4),
    PipelineNode(id="phase4_var",  label="VAR 추정",   description="단기 동적 모형",      phase_number=4),
    PipelineNode(id="phase5",      label="Phase 5",    description="Granger 인과 검정",   phase_number=5),
    PipelineNode(id="phase6",      label="Phase 6",    description="구조 변화 탐지",      phase_number=6),
    PipelineNode(id="phase7",      label="Phase 7",    description="통계 기반 이상 탐지", phase_number=7),
    PipelineNode(id="phase7_ml",   label="Phase 7-ML", description="ML 보조 교차검증",    phase_number=7.5),
    PipelineNode(id="phase8",      label="Phase 8",    description="결과 종합·등급화",    phase_number=8),
]

_PIPELINE_EDGES: list[PipelineEdge] = [
    PipelineEdge(source="phase0",      target="phase1"),
    PipelineEdge(source="phase1",      target="phase2"),
    PipelineEdge(source="phase2",      target="phase3"),
    PipelineEdge(source="phase3",      target="phase4_vecm", label="공적분 있음"),
    PipelineEdge(source="phase3",      target="phase4_var",  label="공적분 없음"),
    PipelineEdge(source="phase4_vecm", target="phase5"),
    PipelineEdge(source="phase4_var",  target="phase5"),
    PipelineEdge(source="phase5",      target="phase6"),
    PipelineEdge(source="phase6",      target="phase7"),
    PipelineEdge(source="phase6",      target="phase7_ml"),
    PipelineEdge(source="phase7",      target="phase8"),
    PipelineEdge(source="phase7_ml",   target="phase8"),
]

_PATTERNS: list[PatternInfo] = [
    PatternInfo(
        pattern_id="pattern1",
        label_kr="패턴 1: 방향 역전 및 시차 이탈",
        description=(
            "국제 원자재 가격이 변동할 때 다음 단계 가격이 반대 방향으로 움직이거나, "
            "정상 전달 시차(IRF 피크 시점 + 버퍼 1개월)를 초과해도 하류가 무반응인 경우"
        ),
        applicable_segments=["A", "B", "C", "D", "D_prime"],
    ),
    PatternInfo(
        pattern_id="pattern2",
        label_kr="패턴 2: 전이율 크기 이탈 및 비대칭 전달(로켓-깃털 효과)",
        description=(
            "전이율이 롤링 Z-score와 IQR 기준을 동시 초과하거나, "
            "TECM/비대칭 VAR에서 상승·하락 조정 속도가 유의미하게 다른 경우"
        ),
        applicable_segments=["A", "B"],
    ),
    PatternInfo(
        pattern_id="pattern3",
        label_kr="패턴 3: 국제가격 안정기 중 하류 물가 스프레드 누적 확대",
        description=(
            "국제가 안정기(원화 환산 월 변동 ±3% 이내)에 "
            "수입단가-PPI 간 수준 괴리가 N개월 연속 같은 방향으로 확대되는 경우"
        ),
        applicable_segments=["B"],
    ),
]


def _compute_etag(data: dict) -> str:
    """응답 본문 SHA-256 해시 앞 16자."""
    body = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def build_pipeline_response() -> tuple[MetaPipelineResponse, str]:
    """GET /meta/pipeline 응답 + ETag 반환."""
    response = MetaPipelineResponse(
        version=_DEFAULTS["pipeline_version"],
        nodes=_PIPELINE_NODES,
        edges=_PIPELINE_EDGES,
    )
    etag = _compute_etag(response.model_dump())
    return response, etag


def build_analysis_params_response() -> tuple[MetaAnalysisParamsResponse, str]:
    """GET /meta/analysis-params 응답 + ETag 반환."""
    response = MetaAnalysisParamsResponse(
        version=_DEFAULTS["pipeline_version"],
        params=AnalysisParams(
            rolling_window=settings.rolling_window,
            zscore_warning=settings.zscore_warning,
            zscore_alert=settings.zscore_alert,
            iqr_multiplier=_DEFAULTS["iqr_multiplier"],
            stability_threshold=_DEFAULTS["stability_threshold"],
            pattern3_n_values=_DEFAULTS["pattern3_n_values"],
            min_subperiod_obs=_DEFAULTS["min_subperiod_obs"],
            lag_search_range=_DEFAULTS["lag_search_range"],
            chow_test_points=_DEFAULTS["chow_test_points"],
        ),
        patterns=_PATTERNS,
    )
    etag = _compute_etag(response.model_dump())
    return response, etag
