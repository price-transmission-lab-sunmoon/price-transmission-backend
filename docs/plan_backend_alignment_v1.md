# 백엔드 코드 ↔ 최신 명세 정합화 플랜 v1

**목적**: 현재 `app/`, `alembic/`, `tests/`, 설정 파일이 `docs/docs_manifest.md` §1 기준 최신 명세 (`frame_spec_backend_v3`, `api_spec_v5`, `db_schema_v5`, `exception_spec_v5`, `exception_design_v3`, `pipeline_output_spec_v7`) 와 정합하도록 수정 항목을 정리한다.
**실행 주체**: 본 플랜은 PM 감사용이며, 실제 코드 생성은 Sonnet이 수행한다.
**작성일**: 2026-05-02
**작성자**: Opus (감사) → Sonnet (실행)
**근거 문서** (본 플랜은 manifest 해석기 대상):
- `frame_spec_backend_vN.md`, `api_spec_vN.md`, `db_schema_vN.md`
- `exception_spec_vN.md`, `exception_design_vN.md`, `pipeline_output_spec_vN.md`
- `docs_manifest.md` §2.2 (파일 부재 방지 규칙)

---

## 0. Sonnet 실행 전 필수 체크 (manifest §2.2 강제)

**이 플랜을 실행하기 전에 반드시 아래 순서로 사전 점검한다. 하나라도 실패하면 즉시 중단하고 PM에게 보고한다.**

1. `docs/docs_manifest.md` 를 먼저 읽는다.
2. manifest §1 버전 해석표의 각 "실제 파일명" 이 `docs/` 폴더에 존재하는지 확인 (12개):
   - `doc1_technical_pipeline_v10.md`, `doc2_pattern_definitions_v2.md`, `doc3_research_proposal_v11.md`, `web_plan_v6.md`, `pipeline_output_spec_v7.md`, `db_schema_v5.md`, `api_spec_v5.md`, `exception_spec_v5.md`, `exception_design_v3.md`, `feature_dev_list_v4.md`, `frame_spec_backend_v3.md`, `frame_spec_frontend_v4.md`
3. `sprint_plan_vN`, `team_ai_collab_vN` 은 미입고 상태(manifest §1.1). **본 플랜의 작업 범위는 이 두 문서에 의존하지 않는다** — 본 플랜 실행에는 제약 없음. 단 코드 주석에서 이 두 문서를 참조할 때는 `sprint_plan_vN.md`, `team_ai_collab_vN.md` 표기만 쓰고 구체 버전 금지.
4. 본 플랜의 **모든 참조 버전은 `_vN` 표기**로 해석하며, 실제 파일명은 manifest §1 표로 매핑한다.

---

## 1. 현재 백엔드 코드 인벤토리 (기준점)

### 1.1 구현 완료 파일 (Frame §2 기준)

```
app/
├── main.py                    ✓ lifespan + CORS + 예외핸들러 + 라우터
├── api/
│   ├── deps.py                ✓ get_db, get_redis
│   └── v1/
│       ├── router.py          ✓ prefix="/api/v1"
│       └── endpoints/
│           ├── anomalies.py   ✓ 6 endpoints (summary, detail, stat-series, stat-snapshot, irf, ml-map)
│           ├── commodities.py ✓ 7 endpoints
│           └── meta.py        ✓ 6 endpoints
├── core/
│   ├── config.py              ✓ Pydantic Settings + Literal + validators
│   ├── exceptions.py          ✓ ProjectError/DBError/APIError/ParseError/ConfigError/ExternalAPIError + 체이닝 + 3 핸들러
│   └── logging.py             ✓ JSON dictConfig
├── db/
│   ├── base.py                ✓ DeclarativeBase + naming convention
│   ├── session.py             ⚠ 2건 이슈(§3.1)
│   └── models/                ✓ 9 tables (commodity, anomaly, timeseries, batch)
├── schemas/                   ✓ 5 files (commodity, anomaly, timeseries, meta, error)
├── cache/redis.py             ✓ ping + lazy init
└── services/.gitkeep          ✓ Frame §8.11 공란 유지
alembic/
├── env.py                     ✓ 비동기 engine + 9개 모델 import
└── versions/
    ├── 0001_initial_frame_tables.py   ✓ 9 tables + indexes + UNIQUE
    └── 0002_seed_reference_data.py    ✓ commodities 10 + segments 5 + events 5
tests/test_frame_smoke.py      ✓ 3건 (app_startup, commodities_dummy, period_validator)
.env.example, pyproject.toml, requirements.txt, alembic.ini  ✓
```

### 1.2 정상 확인 (수정 불필요)

| 항목 | 현황 | 검증 |
|---|---|---|
| 패키지 버전 고정 | `requirements.txt` 19줄 전부 `==` 정확 버전 | Frame §3 일치, 범위 연산자 0건 |
| 환경 변수 | 8개 변수(`.env.example`, `config.py`) | Frame §4 표 완전 일치 |
| ORM 9개 테이블 | `commodities`, `segments`, `external_events`, `raw_prices`, `stat_timeseries`, `anomaly_results`, `asymmetry_results`, `pipeline_runs`, `data_freshness` | Frame §8.6 일치 |
| Alembic revision 2개 | `0001_initial_frame_tables`, `0002_seed_reference_data` | Frame §8.9 일치 |
| DB 컬럼 ↔ Pydantic Literal 3방향 일치 | `cluster`, `route_type`, `confidence_grade`, `primary_pattern`, `pattern_types`, `model_type`, `ect_type`, `granularity` | Frame §6.2·§6.3 일치 |
| 에러 envelope | `{"error": {"code", "message", "context"}}` | api_spec_vN §공통 사항 일치 |
| 라우터 prefix | `APIRouter(prefix="/api/v1")` | Frame §8.3 일치 |
| CORS | `allow_origins=settings.cors_allowed_origins.split(",")` | Frame §8.10 일치 |
| 로깅 JSON 1줄 포맷 | `_JsonFormatter` + `dictConfig` | Frame §8.5 + exception_spec_vN §부록 A 일치 |
| 예외 클래스 계층 | `ProjectError` → `DBError`·`APIError`·`ParseError`·`ConfigError`·`ExternalAPIError` | exception_spec_vN §부록 A 완전 일치 |
| 에러 체이닝 | `trace_error_chain` + `_format_chain` 구현 | exception_design_vN §2.2 일치 |
| 외부 에러 코드 | `COMMODITY_NOT_FOUND`, `ANOMALY_NOT_FOUND`, `INTERNAL_ERROR`, `API-VAL-001` | api_spec_vN §에러 코드 정의 13종 중 현재 구현 필요분 충족 |
| Smoke test 3건 | `test_app_startup`, `test_commodities_dummy`, `test_period_validator` | Frame §7.4 완전 일치 |

**본 플랜은 위 항목을 건드리지 않는다.** 아래 §2~§5 에 나열된 **실제 불일치** 만 수정한다.

---

## 2. 심각도·우선순위 요약

| 우선순위 | 항목 수 | 성격 | 배치 |
|---|---|---|---|
| **P0 — Critical (런타임 실패 가능)** | 1 | DB 드라이버 설정 오류 | §3.1 |
| **P1 — High (사양 직접 위반)** | 3 | 타입 오류·버전 문자열·함수 중복 | §3 |
| **P2 — Medium (기능 불완전)** | 3 | 응답 타입 미정의·Literal 미적용·향후 feat 연결 | §4 |
| **P3 — Low (표기·주석 — manifest §2.1 위반)** | 18건 파일 across 17 files | 스테일 버전 주석 (`_v3/v4/v5/v2`) | §5 |

---

## 3. P0 ~ P1 수정 (실행 순서대로)

### 3.1 [P0] `app/db/session.py` — asyncpg `statement_timeout` 설정 오류

**현상**:
```python
engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    connect_args={"statement_timeout": "30000"},  # ❌ asyncpg는 이 키를 받지 않음
    echo=settings.app_env == "development",
)
```

**문제**: asyncpg는 `connect` 인자로 `statement_timeout`을 직접 받지 않는다. PostgreSQL 서버 세션 설정은 `server_settings` 딕셔너리로 전달해야 한다. 현재 코드는 실제 PostgreSQL 연결 시 `TypeError` 또는 설정 무시로 이어질 가능성이 매우 높다 (개발 모드에서 DB 없이 기동하면 드러나지 않아 지금까지 숨어 있음).

**수정**:
```python
engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    connect_args={
        "server_settings": {"statement_timeout": "30000"},  # PostgreSQL 측 세션 설정
    },
    echo=settings.app_env == "development",
)
```

**근거**: frame_spec_backend_vN §5 "쿼리 타임아웃 30초 (statement_timeout)". 값은 ms 문자열 유지("30000").

**검증**: 실 PostgreSQL 연결 후 `SHOW statement_timeout;` 결과가 `30s` 또는 `30000`이면 성공. 연결 실패 메시지(`TypeError: connect() got an unexpected keyword argument 'statement_timeout'` 등) 재현 시 수정 확인 가능.

### 3.2 [P1] `app/db/session.py` — `get_db()` 타입 오류 + 중복 정의

**현상**:
```python
# app/db/session.py
async def get_db() -> AsyncSession:          # ❌ yield인데 AsyncSession 반환 타입
    async with AsyncSessionLocal() as session:
        yield session
```

```python
# app/api/deps.py
async def get_db() -> AsyncGenerator[AsyncSession, None]:   # ✓ 올바름
    async with AsyncSessionLocal() as session:
        yield session
```

**문제 A (타입 오류)**: `session.py::get_db()` 의 타입 어노테이션은 `AsyncGenerator[AsyncSession, None]` 이어야 한다. 현재는 ruff/mypy가 타입 검증을 수행하면 실패한다.

**문제 B (중복 정의)**: 동일 이름의 `get_db()` 가 `session.py` 와 `deps.py` 두 군데에 존재. FastAPI `Depends()` 사용 시 어느 쪽을 import 했는지 혼동 유발. 의존성 주입의 SoT는 `app/api/deps.py` 여야 한다 (Frame §2 구조).

**수정**:
1. `app/db/session.py` 에서 `get_db()` **함수 자체 제거**. `engine` 과 `AsyncSessionLocal` 정의만 유지.
2. `app/api/deps.py` 의 `get_db()` 를 유일한 의존성 주입 진입점으로 유지.

**검증**:
- `grep -rn "def get_db" app/` 결과 `app/api/deps.py:11` 1건만 나와야 한다.
- `ruff check app/` 통과.

### 3.3 [P1] `/meta/pipeline`, `/meta/analysis-params` — `version` 필드 구현 방침 정정

**현상**:
```python
# app/api/v1/endpoints/meta.py
return MetaPipelineResponse(version="v9", ...)        # line 86
return MetaAnalysisParamsResponse(version="v9", ...)  # line 121
```

**문제**:
- manifest §1 기준 현재 `doc1_technical_pipeline` 은 **v10**.
- api_spec_vN §방법론 엔드포인트 예시 JSON 은 `"version": "v8"` 로 기재되어 있으나, 이는 **api_spec 작성 당시의 doc1 버전** (spec 자체의 스테일 예시). 응답 `version` 필드의 **의미론적 출처는 `doc1_technical_pipeline`** 이다.
- 코드 `"v9"` 는 과거 doc1 v9 시점 값으로 현재 스테일.

**수정 전략** (둘 중 택일; Sonnet은 **옵션 B 권장**):

**옵션 A — 단순 하드코딩 갱신**:
```python
return MetaPipelineResponse(version="v10", ...)
return MetaAnalysisParamsResponse(version="v10", ...)
```
장점: 즉시 수정. 단점: doc1 버전 올라갈 때마다 수동 수정 필요.

**옵션 B — 설정 상수화 (권장)**:
1. `app/core/config.py` 의 `Settings` 에 상수 추가:
   ```python
   pipeline_spec_version: str = "v10"  # doc1_technical_pipeline 현재 버전
   ```
2. `.env.example` 과 `config.py` 주석으로 manifest §1 표 참조 명시:
   ```
   # PIPELINE_SPEC_VERSION: docs/docs_manifest.md §1 doc1_technical_pipeline 현재 버전과 일치해야 함
   PIPELINE_SPEC_VERSION=v10
   ```
3. `meta.py` 에서 `settings.pipeline_spec_version` 주입.

**근거**: manifest §2.1 규칙 — 구체 버전 하드코딩 금지. 옵션 B는 버전 해석을 환경 변수로 추출해 manifest 갱신과 함께 한 곳만 고치게 한다.

**검증**:
- `GET /api/v1/meta/pipeline` 응답 `version == "v10"`
- `GET /api/v1/meta/analysis-params` 응답 `version == "v10"`
- `test_frame_smoke.py` 는 `version` 키 존재만 검증하므로 그대로 통과

### 3.4 [P1] `exception_spec_vN §부록 A` vs Frame `§8.4 골격` 차이 — `PipelineError` 처리

**현상**: Frame `§8.4` 예시 코드 블록에는 `PipelineError(ProjectError)` 가 있으나 (`PL-*` 코드용), 실제 `app/core/exceptions.py` 에는 없다. 또한 exception_spec_vN `§부록 A` 공식 계층도 `PipelineError` 를 포함하지 않는다 — Frame 예시가 exception_spec 보다 과도하게 기재된 상태.

**문제**: 현재 Frame 단계는 `services/` 가 비어있어(§8.11) `PipelineError` 가 즉시 필요치 않다. 그러나 후속 `feat/pipeline-phase*` 착수 시 `PL-P2-001` 같은 코드를 `ProjectError` 로만 던지면 `phase` 속성 부재로 디버깅 컨텍스트가 약해진다.

**수정 전략** (Sonnet: **옵션 B 권장**):

**옵션 A — 변경 없음**:
Frame 단계는 엄격히 exception_spec_vN §부록 A만 구현. `PipelineError` 는 해당 feat 브랜치에서 도입. 이때 exception_spec_vN 도 함께 갱신.

**옵션 B — 선반영 (권장)**:
`app/core/exceptions.py` 에 아래 클래스 추가. exception_spec_vN §부록 A 에도 동일 클래스를 선반영하도록 PM에게 요청 (spec 갱신은 별도 PR).
```python
class PipelineError(ProjectError):
    """파이프라인 단계 예외 (PL-*). phase 속성 필수."""
    def __init__(self, code: str, message: str, context: dict | None = None, phase: str = ""):
        super().__init__(code, message, context)
        self.phase = phase
```
또한 `internal_error_handler` 의 분기에 `PipelineError` 도 `INTERNAL_ERROR` 500 으로 분류 (현재 캐치올 `Exception` 핸들러가 처리하므로 동작 변화 없음, 단 로그에 `phase` 필드 포함되도록 `exc.phase` 를 extra 로 추가).

**근거**: Frame §8.4 골격은 "예시" 로 제시됐으나 `feat/pipeline-phase*` 가 곧 착수되므로 **선반영 옵션이 실용적**. exception_spec_vN 업데이트는 PM에게 별건 요청.

**이슈 기록**: exception_spec_vN `§부록 A` 와 Frame §8.4 골격 간 불일치는 별도 spec 갱신 PR로 처리. 본 플랜 범위 밖이지만 PM에게 공지 필요.

---

## 4. P2 중간 우선순위 개선

### 4.1 [P2] `/anomalies/{id}/stat-snapshot`, `/irf`, `/ml-map` — Pydantic 응답 스키마 부재

**현상**: `app/api/v1/endpoints/anomalies.py` 의 3개 엔드포인트는 `-> dict` 로 선언되어 Pydantic 모델 검증 없이 원시 dict 반환.

**spec**: api_spec_vN §패널 엔드포인트 (line 787~922) 는 세 엔드포인트 모두 **구체적 JSON 구조** 를 정의한다 (예: `/stat-snapshot` 은 `metric=iqr` 일 때 `boxplot`, `metric=asymmetry` 일 때 `histogram` 등 분기 구조).

**수정**:
1. `app/schemas/anomaly.py` (또는 별도 `app/schemas/panel.py`) 에 아래 Pydantic 모델 추가:
   - `StatSnapshotIQRResponse`, `StatSnapshotAsymmetryResponse`, 그리고 `StatSnapshotResponse = StatSnapshotIQRResponse | StatSnapshotAsymmetryResponse` (또는 `Annotated[Union[...], Discriminator("metric")]`)
   - `IRFResponse` — api_spec_vN §837~881 구조
   - `MLMapResponse` — api_spec_vN §883~921 구조
2. endpoint 함수 시그니처 `-> dict` → `-> StatSnapshotResponse` 등으로 교체.
3. Frame 단계 dummy 응답은 `total_points=0`, `points=[]`, `curves=[]` 등 빈 상태 유지.

**검증**: `response_model=...` 지정 시 Pydantic 이 응답 검증을 자동 수행. FastAPI OpenAPI (`/docs`) 에 스키마 노출 확인.

### 4.2 [P2] `/anomalies/{id}/ml-map` `model` 쿼리 파라미터 — `Literal` 미적용

**현상**:
```python
async def get_ml_map(anomaly_id: int, model: str = "isolation_forest") -> dict:
```

**spec**: api_spec_vN §ml-map 은 `model` 값 3종(`isolation_forest`, `lof`, `oneclass_svm`) 을 명시.

**수정**:
```python
from typing import Literal

async def get_ml_map(
    anomaly_id: int,
    model: Literal["isolation_forest", "lof", "oneclass_svm"] = "isolation_forest",
) -> MLMapResponse:
```

**동일 적용 필요 위치**:
- `/anomalies/{id}/stat-series` `metric`: Literal 타입으로 제약 (`transmission_rate`, `rolling_mean`, `zscore`, `breakpoints` 등 api_spec 값 목록 기준)
- `/anomalies/{id}/stat-snapshot` `metric`: `Literal["iqr", "asymmetry"]`
- `/commodities/{id}/raw-prices` `layout`: `int` → 경계 검증은 `Query(ge=1, le=6)` 사용

**근거**: Frame §6.3 Literal 사용 원칙 — 고정 enum 성격 필드는 반드시 `Literal` 로 선언.

**검증**: 허용 외 값 요청 시 FastAPI 가 자동으로 422 반환 (`API-VAL-001`). smoke test는 기존대로 통과.

### 4.3 [P2] `/commodities/{id}/scatter` — `segment_id` 쿼리 파라미터 누락

**현상**:
```python
@router.get("/commodities/{commodity_id}/scatter", response_model=ScatterResponse)
async def get_scatter(commodity_id: str) -> ScatterResponse:
    ...
    return ScatterResponse(
        commodity_id=commodity_id,
        segment_id="A",                         # ❌ 하드코딩
        ...
    )
```

**spec**: api_spec_vN §439~487 (`/scatter`) 는 `segment_id` 쿼리 파라미터를 **필수** 로 요구 (3구간 / 4구간 에 따라 A/B/C/D/D_prime 중 선택).

**수정**:
```python
async def get_scatter(
    commodity_id: str,
    segment_id: Literal["A", "B", "C", "D", "D_prime"],  # 필수
) -> ScatterResponse:
    # 3seg 품목에 C, D 요청 시 INVALID_SEGMENT (D-12)
    commodity = _COMMODITY_MAP.get(commodity_id)
    if not commodity:
        raise APIError("API-COM-001", "...", http_status=404, public_code="COMMODITY_NOT_FOUND", context={"commodity_id": commodity_id})
    if segment_id not in commodity["segments"]:
        raise APIError(
            "API-SEG-001",
            "해당 품목에 존재하지 않는 구간입니다.",
            context={"commodity_id": commodity_id, "requested_segment": segment_id, "available_segments": commodity["segments"]},
            http_status=400,
            public_code="INVALID_SEGMENT",
        )
    return ScatterResponse(commodity_id=commodity_id, segment_id=segment_id, ...)
```

**근거**: api_spec_vN §439 + D-12. 에러 코드 `INVALID_SEGMENT` 는 api_spec_vN §에러 코드 정의 13종 중 하나 (400).

**검증**: `/scatter?segment_id=X` (품목에 X 구간 없음) 호출 시 400 + `error.code == "INVALID_SEGMENT"`.

---

## 5. P3 스테일 버전 주석 정정 (manifest §2.1 위반)

**원칙**: 모든 코드 주석 / docstring / 문자열 상수의 `_v[0-9]+` 표기를 `_vN` 으로 전환. 단 **실제 응답 필드값·외부 식별자**(예: `pipeline_spec_version`) 는 §3.3 방식으로 처리하고, 주석만 `_vN` 로 전환하는 항목은 본 §5 에 해당.

### 5.1 수정 대상 파일 목록 (16 파일)

| # | 파일 | 현재 스테일 표기 | 수정 후 |
|---|---|---|---|
| 1 | `.env.example` | `pipeline_output_spec_v5 §파라미터 표` | `pipeline_output_spec_vN §파라미터 표` |
| 2 | `app/core/config.py` | `pipeline_output_spec_v5 §파라미터 표, CFG-CORE-003` | `pipeline_output_spec_vN §파라미터 표, CFG-CORE-003` |
| 3 | `app/core/exceptions.py` (line 1) | `exception_spec_v4 §부록 A + exception_design_v2 §2 구현` | `exception_spec_vN §부록 A + exception_design_vN §2 구현` |
| 4 | `app/core/exceptions.py` (line 13 comment) | `(exception_spec_v4 §부록 A)` | `(exception_spec_vN §부록 A)` |
| 5 | `app/core/exceptions.py` (line 70 comment) | `(exception_design_v2 §2)` | `(exception_design_vN §2)` |
| 6 | `app/core/exceptions.py` (line 124 comment) | `(exception_design_v2 §2.4 + frame_spec §8.4)` | `(exception_design_vN §2.4 + frame_spec_backend_vN §8.4)` |
| 7 | `app/core/exceptions.py` (line 161 docstring) | `exception_spec_v4 §4 API-INT-001, exception_design_v2 §2.4` | `exception_spec_vN §4 API-INT-001, exception_design_vN §2.4` |
| 8 | `app/core/logging.py` (line 1) | `exception_spec_v2 §부록 A 예시 형식` | `exception_spec_vN §부록 A 예시 형식` |
| 9 | `app/cache/redis.py` (line 1) | `exception_spec_v2 DB-CACHE-001 대응` | `exception_spec_vN DB-CACHE-001 대응` |
| 10 | `app/api/v1/router.py` (line 1) | `api_spec_v4 §공통 사항` | `api_spec_vN §공통 사항` |
| 11 | `app/api/v1/endpoints/commodities.py` (line 15, 43) | `db_schema_v3 §commodities 초기 데이터` | `db_schema_vN §commodities 초기 데이터` |
| 12 | `app/api/v1/endpoints/meta.py` (line 56, 70, 84) | `db_schema_v3`(×2), `api_spec_v4 §방법론 엔드포인트` | 모두 `_vN` |
| 13 | `app/schemas/commodity.py` (line 1) | `api_spec_v4 1:1 대응` | `api_spec_vN 1:1 대응` |
| 14 | `app/schemas/error.py` (line 1) | `api_spec_v4 §공통 사항 + exception_spec_v2 §부록 A` | `api_spec_vN §공통 사항 + exception_spec_vN §부록 A` |
| 15 | `app/db/models/commodity.py` (line 1) | `db_schema_v3 §참조 테이블` | `db_schema_vN §참조 테이블` |
| 16 | `app/db/models/anomaly.py` (line 1, 75) | `db_schema_v3 §이상 탐지 테이블`, `db_schema_v3 §anomaly_results` | 모두 `_vN` |
| 17 | `app/db/models/timeseries.py` (line 1, 66, 170) | `db_schema_v3 §탐지/원시가격 테이블`, `db_schema_v3: period DESC`(×2) | 모두 `_vN` |
| 18 | `app/db/models/batch.py` (line 1) | `db_schema_v3 §배치 관리 테이블` | `db_schema_vN §배치 관리 테이블` |
| 19 | `alembic/versions/0001_initial_frame_tables.py` | `db_schema_v3 기준`(×1), `db_schema_v3 §anomaly_results 인덱스`(×1), `db_schema_v3: period DESC`(×2), `db_schema_v3 §anomaly_results 인덱스 3종`(×1) | 모두 `_vN` |
| 20 | `alembic/versions/0002_seed_reference_data.py` | `db_schema_v3 §초기 데이터`(×1), `db_schema_v3 §commodities 초기 데이터`(×1), `db_schema_v3 §segments 초기 데이터`(×1), `db_schema_v3 §external_events 초기 데이터`(×1) | 모두 `_vN` |

### 5.2 일괄 치환 주의점

- 치환은 **주석·docstring·문자열 내부의 `_v[0-9]+`** 에만 적용한다.
- `pipeline_runs` 테이블 컬럼값 등 **실 데이터** 는 건드리지 않는다.
- 각 alembic revision 의 `revision: str = "0001"`/`"0002"` 값은 **버전이 아님** (alembic 자체 ID). 절대 수정 금지.
- `test_frame_smoke.py` 는 버전 주석 없음 (확인 완료). 수정 대상 아님.

### 5.3 검증

실행 후 전체 수정이 끝났는지 확인:
```powershell
rg "_v[0-9]" app/ alembic/ tests/ .env.example | Select-String -NotMatch "revision:"
```
결과가 **0건** 이어야 한다 (alembic revision ID 제외).

---

## 6. 실행 순서 (Sonnet 작업 흐름)

각 단계는 **다음 단계 진입 전** 로컬 `pytest` 통과 + `ruff check app/ alembic/ tests/` 통과를 확인한다.

### Phase 1 — 안전 기반 확보 (P0, P1)
1. §3.1 `db/session.py` asyncpg `server_settings` 수정
2. §3.2 `db/session.py` `get_db()` 제거 (deps.py 로 일원화)
3. §3.3 `/meta/pipeline`·`/meta/analysis-params` `version` 상수화 (옵션 B)
4. **검증**: `pytest` 3건 통과 + `uvicorn app.main:app` 기동 + `/api/v1/meta/pipeline` 응답 `version == "v10"`

### Phase 2 — 응답 스키마 강화 (P2)
5. §4.1 panel 응답 스키마 3종 추가 (`StatSnapshotResponse`, `IRFResponse`, `MLMapResponse`)
6. §4.2 `Literal` 쿼리 파라미터 적용 (ml-map `model`, stat-series `metric`, stat-snapshot `metric`)
7. §4.3 `/scatter` `segment_id` 필수 쿼리 파라미터 + `INVALID_SEGMENT` 예외 처리
8. **검증**: `pytest` 통과 + 새 엔드포인트 수동 호출 (OpenAPI /docs 로 스키마 확인)
9. **추가 스모크 테스트 제안** (선택, 별도 PR 가능):
   - `test_scatter_invalid_segment`: 3구간 품목(wheat)에 `segment_id=C` 요청 시 400 + `INVALID_SEGMENT`
   - `test_ml_map_invalid_model`: `model=xgboost` 요청 시 422

### Phase 3 — 예외 계층 선반영 (P1, 옵션 B 선택 시)
10. §3.4 `PipelineError` 클래스 추가 + `internal_error_handler` 에 `phase` extra 반영
11. **검증**: `pytest` 통과

### Phase 4 — 주석 일괄 정정 (P3)
12. §5.1 표 순서대로 16 파일 수정 (일괄 치환 가능, 단 §5.2 주의점 준수)
13. **검증**: §5.3 rg 결과 0건

### Phase 5 — 최종 통합 검증
14. `ruff check .` + `ruff format --check .` 통과
15. `alembic upgrade head` (실 PostgreSQL 연결 시) 오류 없이 완료
16. `/api/v1/meta/config` 응답 `db_status == "ok"`, `redis_status == "ok"` (실 서비스 연결 시)
17. Frame §9 PM 승인 체크리스트 9개 항목 재확인

---

## 7. 본 플랜이 **수정하지 않는** 항목 (근거 명시)

| 항목 | 이유 |
|---|---|
| `app/services/` 비어있음 | Frame §8.11: ML 및 파이프라인 로직은 후속 `feat/pipeline-phase*` 담당 |
| `raw_prices` 테이블 데이터 미적재 | Frame 단계는 시드 데이터(commodities 10/segments 5/events 5) 만 로딩. 가격 데이터는 `feat/be-data-ingestion` 담당 |
| `stationarity_results`, `cointegration_results`, `model_params`, `irf_data`, `baselines`, `granger_results`, `breakpoints`, `subperiods`, `ml_scores`, `ml_projections`, `mv_anomaly_density_yearly` 테이블 없음 | Frame §8.6: 9개 테이블만 Frame 범위. 나머지 10 테이블 + mv 1개는 해당 feat 브랜치 담당 |
| Redis 캐싱 실구현 | Frame 단계는 ping만. 캐시 키 규칙·TTL 은 api_spec_vN §미결 사항 (OI-15 이후) |
| APScheduler 배치 로직 | `feat/be-batch-scheduler` 담당 |
| `frame_spec_backend_vN §8.4 골격` 이 exception_spec_vN §부록 A 와 다른 점 (PipelineError 유무) | §3.4 옵션 B 선택 시 코드 선반영. spec 자체 갱신은 별도 PR (PM 결정 사항) |
| api_spec_vN §방법론 엔드포인트 예시 `"version": "v8"` (스테일) | 이는 spec 본문의 stale 사례. §3.3 수정은 코드 측만 정정. spec 본문 수정은 별건 — PM에게 공지 |

---

## 8. 리스크 및 오픈 이슈

| 리스크 | 확률 | 영향 | 완화책 |
|---|---|---|---|
| §3.1 asyncpg `server_settings` 수정 후 다른 설정 호환 문제 | 낮음 | 중 | `APP_ENV=development` 로 DB 미연결 기동 먼저 검증 후 실 DB 연결 |
| §3.3 옵션 B 선택 시 `.env.example` 에 신규 `PIPELINE_SPEC_VERSION` 추가 → Frame §4 환경 변수 표와 불일치 | 중 | 낮음 | Frame §4 갱신을 PM에게 요청 (`docs/frame_spec_backend_vN` minor bump) |
| §4.1 응답 스키마 변경이 프론트엔드와 contract 차이 유발 | 낮음 | 중 | 프론트 repo 의 `src/types/panel.ts` 와 3방향 대조 필요. Frame §6.2 표에 panel 응답 추가 요청 |
| §5 일괄 치환이 historical 변경이력 주석까지 잘못 건드림 | 중 | 낮음 | 코드 파일에는 historical changelog 가 없음 (확인 완료). 단 혹시 포함되면 `_v[0-9]+` 패턴을 쓰되 "당시 doc1 v9" 같은 historical 표현은 보존. |

---

## 9. PM 별건 요청 사항 (본 플랜 범위 외, 추후 처리)

1. **`exception_spec_vN` §부록 A 에 `PipelineError` 클래스 선반영** — §3.4 옵션 B 선택 시 spec 측도 일관되게 갱신 (`exception_spec_v5 → v6` 형태의 minor bump).
2. **`api_spec_vN §방법론 엔드포인트` 예시 `"version"` 필드 설명 보강** — 값이 `doc1_technical_pipeline` 의 현재 버전을 echo한다는 점을 spec 에 명시. 예시는 `"version": "<doc1 current>"` 처럼 placeholder 표기.
3. **`frame_spec_backend_vN §4` 환경 변수 표에 `PIPELINE_SPEC_VERSION` 추가** — §3.3 옵션 B 채택 시.
4. **`frame_spec_backend_vN §6.2` 3방향 타입 일치 표에 panel 응답 추가** — §4.1 스키마 신설에 맞춰.

---

## 10. 변경 이력

- v1 (2026-05-02): 최초 작성. `docs/docs_manifest.md` v1 기반 백엔드 코드 감사 결과를 Sonnet 실행용 플랜으로 정리. P0 1건 / P1 3건 / P2 3건 / P3 16 파일 분류.

---

*본 플랜 실행 후, Sonnet 은 `docs/docs_manifest.md` §6 변경 이력에 본 플랜 실행 완료 기록 1줄 추가를 요청한다 (별도 플랜 PR 커밋 메시지로 대체 가능).*
