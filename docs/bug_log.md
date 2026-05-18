# 버그 기록 (Bug Log)

백엔드 통합 브랜치(`backend/merge_all`) 기준으로 발견·수정된 버그를 기록합니다.

---

## 기록 규칙

- **발견 경로**: 정적 분석 / 서버 실행 / 테스트 / 런타임
- **에러 코드**: `exception_spec_v6.md` 기준 코드 (해당 시)
- **상태**: `수정완료` / `미해결` / `스텁(의도적)`

---

## BUG-001 · anomaly_panel.py — APIError 잘못된 파라미터명

| 항목 | 내용 |
|---|---|
| **파일** | `app/services/anomaly_panel.py` |
| **발견 경로** | 정적 분석 (2026-05-18) |
| **증상** | 모듈 import 시 `TypeError: APIError.__init__() got unexpected keyword argument 'status_code'` |
| **원인** | `APIError` 생성자는 `code`, `http_status` 파라미터를 받지만, `status_code=501`, `error_code="..."` 로 잘못 전달 |
| **수정** | `code="API-INT-NOT-IMPLEMENTED"`, `http_status=501`, `public_code="NOT_IMPLEMENTED"` 로 수정 |
| **상태** | 수정완료 |

```python
# Before (오류)
_NOT_IMPLEMENTED = APIError(
    status_code=501,
    error_code="API-INT-NOT-IMPLEMENTED",
    message="...",
)

# After (수정)
_NOT_IMPLEMENTED = APIError(
    code="API-INT-NOT-IMPLEMENTED",
    message="...",
    http_status=501,
    public_code="NOT_IMPLEMENTED",
)
```

---

## BUG-002 · meta.py — etag_header 미정의 변수 (NameError)

| 항목 | 내용 |
|---|---|
| **파일** | `app/api/v1/endpoints/meta.py` |
| **발견 경로** | 정적 분석 (2026-05-18) |
| **증상** | `GET /events`, `GET /segments` 호출 시 `NameError: name 'etag_header' is not defined` |
| **원인** | `etag` 변수로 반환받았으나 `JSONResponse` headers에서 미정의 `etag_header` 변수 참조 |
| **수정** | `etag_header` → `f'"{etag}"'` 로 수정 (두 엔드포인트 모두) |
| **상태** | 수정완료 |

```python
# Before (오류)
headers={"ETag": etag_header, "Cache-Control": _CACHE_CONTROL}

# After (수정)
headers={"ETag": f'"{etag}"', "Cache-Control": _CACHE_CONTROL}
```

---

## BUG-003 · meta.py — PipelineNode / PipelineEdge / PatternInfo import 누락

| 항목 | 내용 |
|---|---|
| **파일** | `app/api/v1/endpoints/meta.py` |
| **발견 경로** | 정적 분석 (2026-05-18) |
| **증상** | `GET /meta/pipeline`, `GET /meta/analysis-params` 호출 시 `NameError: name 'PipelineNode' is not defined` |
| **원인** | `app.schemas.meta` 에 정의된 세 클래스가 endpoint 파일에서 import 누락 |
| **수정** | `from app.schemas.meta import ..., PatternInfo, PipelineEdge, PipelineNode` 추가 |
| **상태** | 수정완료 |

---

## BUG-004 · models/reference.py — ORM 모델 중복 정의 (InvalidRequestError)

| 항목 | 내용 |
|---|---|
| **파일** | `app/db/models/reference.py` |
| **발견 경로** | 서버 실행 (2026-05-18) |
| **증상** | `sqlalchemy.exc.InvalidRequestError: Table 'baselines' is already defined for this MetaData instance` |
| **원인** | `Baseline`, `CointegrationResult` 가 세 파일에 중복 정의됨: `reference.py`(임시), `phase4_5.py`, `phase2_3.py` + `anomaly.py` |
| **수정** | `reference.py` 의 중복 클래스 정의 제거, `anomaly.py` (로드 순서상 먼저 등록되는 정식 정의)에서 re-export |
| **상태** | 수정완료 |

```python
# Before (오류): reference.py 에 독립 클래스 정의
class Baseline(Base):
    __tablename__ = "baselines"
    ...
class CointegrationResult(Base):
    __tablename__ = "cointegration_results"
    ...

# After (수정): anomaly.py 에서 re-export
from app.db.models.anomaly import Baseline, CointegrationResult  # noqa: F401
```

---

## BUG-005 · meta.py — JSONResponse | Response 반환 타입 FastAPI 오류

| 항목 | 내용 |
|---|---|
| **파일** | `app/api/v1/endpoints/meta.py` |
| **발견 경로** | 서버 실행 (2026-05-18) |
| **증상** | `fastapi.exceptions.FastAPIError: Invalid args for response field! ... starlette.responses.JSONResponse \| Response is a valid Pydantic field type` |
| **원인** | FastAPI가 `-> JSONResponse \| Response` 반환 타입 어노테이션에서 response_model을 자동 추론 시도 |
| **수정** | `/freshness`, `/events`, `/segments` 라우트 데코레이터에 `response_model=None` 추가 |
| **상태** | 수정완료 |

```python
# Before (오류)
@router.get("/events")
async def get_events(...) -> JSONResponse | Response:

# After (수정)
@router.get("/events", response_model=None)
async def get_events(...) -> JSONResponse | Response:
```

---

## BUG-006 · logging.py — Windows cp949 콘솔 UnicodeEncodeError

| 항목 | 내용 |
|---|---|
| **파일** | `app/core/logging.py` |
| **발견 경로** | 서버 실행 (2026-05-18) |
| **증상** | 서버 기동 시 `--- Logging error ---` / `UnicodeEncodeError: 'cp949' codec can't encode character '—'` 반복 출력 |
| **원인** | Windows 한국어 터미널 기본 인코딩이 cp949인데, 로그 메시지에 em dash(`—`, U+2014) 포함 |
| **수정** | `setup_logging()` 에서 `StreamHandler`에 UTF-8 `TextIOWrapper` 스트림을 직접 주입 |
| **상태** | 수정완료 |

```python
# After (수정): logging.py setup_logging()
utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
handler = logging.StreamHandler(utf8_stdout)
```

---

## BUG-007 · exceptions.py — api_error_handler context 누락

| 항목 | 내용 |
|---|---|
| **파일** | `app/core/exceptions.py` |
| **발견 경로** | 테스트 실패 (2026-05-18) |
| **증상** | `test_api_error_handler` 에서 `'context' not in body` AssertionError |
| **원인** | `api_error_handler`에서 `_error_body(exc.public_code, exc.message)` — context 인자 미전달 |
| **수정** | `_error_body(exc.public_code, exc.message, exc.context or None)` 로 수정 |
| **상태** | 수정완료 |

---

## BUG-008 · batch.py — cache_delete_pattern lazy import로 patch 불가

| 항목 | 내용 |
|---|---|
| **파일** | `app/services/batch.py` |
| **발견 경로** | 테스트 실패 (2026-05-18) |
| **증상** | `AttributeError: module 'app.services.batch' has no attribute 'cache_delete_pattern'` |
| **원인** | `invalidate_cache()` 함수 내부에서 lazy import → `patch(...)` 가 모듈 속성을 찾지 못함 |
| **수정** | `from app.cache.redis import cache_delete_pattern, get_redis_client` 를 모듈 최상단으로 이동 |
| **상태** | 수정완료 |

---

## BUG-009 · test_frame_smoke.py — /commodities 실 DB 호출로 OSError

| 항목 | 내용 |
|---|---|
| **파일** | `tests/test_frame_smoke.py` |
| **발견 경로** | 테스트 실패 (2026-05-18) |
| **증상** | `OSError: [Errno 42] Illegal byte sequence` — asyncpg가 실제 DB 연결 시도 |
| **원인** | `feat/be-api-reference` 머지 이후 `/commodities` 엔드포인트가 실 DB 쿼리로 전환됐으나 테스트에 mock 미적용 |
| **수정** | `app.dependency_overrides[get_db]` + `patch("app.services.reference.get_commodities", AsyncMock)` 로 서비스 레이어 mock 처리 |
| **상태** | 수정완료 |

---
