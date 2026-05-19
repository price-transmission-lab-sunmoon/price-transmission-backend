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

## BUG-010 · test_redis_cache.py — AsyncMock scan_iter RuntimeWarning

| 항목 | 내용 |
|---|---|
| **파일** | `tests/test_redis_cache.py` |
| **발견 경로** | pytest 경고 (2026-05-19) |
| **증상** | `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` |
| **원인** | `client.scan_iter.side_effect = ConnectionError(...)` 설정 시 AsyncMock이 async generator 대신 coroutine을 반환하여 `async for` 루프에서 await 없이 버려짐 |
| **수정** | `side_effect` 대신 `async def mock_scan_iter_raise(...)` async generator 함수 직접 할당 |
| **상태** | 수정완료 |

```python
# Before (경고)
client.scan_iter.side_effect = ConnectionError("Redis down")

# After (수정)
async def mock_scan_iter_raise(match, count):
    raise ConnectionError("Redis down")
    yield  # async generator 마커
client.scan_iter = mock_scan_iter_raise
```

---

## BUG-011 · phase2_stationarity_test.py — 빈 결과 시 KeyError

| 항목 | 내용 |
|---|---|
| **파일** | `pipeline/preprocessing/phase2_stationarity_test.py` |
| **발견 경로** | 배치 실행 (2026-05-19) |
| **증상** | 입력 데이터 없을 때 `KeyError: 'integration_order'` → 배치 Phase 2 실패 |
| **원인** | `all_results=[]` → `pd.DataFrame([])` → 요약 통계에서 `df["integration_order"]` 접근 시 KeyError (빈 DataFrame에 컬럼 없음) |
| **수정** | `total == 0` 조기 반환 가드 추가 |
| **상태** | 수정완료 |

---

## BUG-012 · phase3_cointegration_test.py — 빈 결과 시 KeyError

| 항목 | 내용 |
|---|---|
| **파일** | `pipeline/preprocessing/phase3_cointegration_test.py` |
| **발견 경로** | 배치 실행 (2026-05-19) |
| **증상** | 입력 데이터 없을 때 `KeyError: 'model_selected'` 계열 → 배치 Phase 3 실패 |
| **원인** | BUG-011과 동일 패턴 — `all_results=[]` → 빈 DataFrame 컬럼 접근 |
| **수정** | `total == 0` 조기 반환 가드 추가 |
| **상태** | 수정완료 |

---

## BUG-013 · phase4_model_estimation.py — 빈 결과 시 KeyError

| 항목 | 내용 |
|---|---|
| **파일** | `pipeline/preprocessing/phase4_model_estimation.py` |
| **발견 경로** | 배치 실행 (2026-05-19) |
| **증상** | 입력 데이터 없을 때 `KeyError: 'peak_horizon'` → 배치 Phase 4 실패 |
| **원인** | `summary_rows=[]` → `pd.DataFrame([])` → `df["peak_horizon"].notna()` 접근 시 KeyError |
| **수정** | `summary_df.empty` 조기 반환 가드 추가 |
| **상태** | 수정완료 |

---

## BUG-014 · phase5_granger_causality.py — 빈 결과 시 IndexError

| 항목 | 내용 |
|---|---|
| **파일** | `pipeline/preprocessing/phase5_granger_causality.py` |
| **발견 경로** | 정적 분석 (2026-05-19) |
| **증상** | 4구간 품목이 없을 때 `rows[0]` IndexError 및 `ppi_row / ws_row` 리스트 인덱싱 실패 |
| **원인** | `all_results=[]` 시 요약 출력 루프에서 인덱스 접근 (경계 검사 없음) |
| **수정** | `not all_results` 조기 반환 가드 + 개별 rows 존재 여부 체크 + `next(..., None)` 안전 접근 |
| **상태** | 수정완료 |

---

## BUG-015 · loader/phase2~5.py — 빈 CSV 읽기 시 배치 실패

| 항목 | 내용 |
|---|---|
| **파일** | `app/db/loader/phase2.py`, `phase3.py`, `phase5.py` |
| **발견 경로** | 배치 실행 (2026-05-19) |
| **증상** | 파이프라인이 빈 CSV를 생성했을 때 `pd.read_csv` → `EmptyDataError` → `DBError` → 배치 `failed` |
| **원인** | `pd.read_csv(empty_file)` 가 `EmptyDataError`를 던지지만 loader에서 미처리, 전체 배치 실패로 전파 |
| **수정** | `pd.errors.EmptyDataError` 별도 catch → WARN 로그 + `return 0` (skip). 비정상 오류만 DBError 재발생 |
| **상태** | 수정완료 |

```python
# After (수정): phase2/3/5 loader 동일 패턴
try:
    df = pd.read_csv(csv_path)
except pd.errors.EmptyDataError:
    logger.warning("CSV 비어있음 — 적재 건너뜀", ...)
    return 0
except Exception as e:
    raise DBError("DB-TX-001", ...) from e
```

---

## BUG-016 · 파이프라인 통합 — config/commodity_mapping.json 누락

| 항목 | 내용 |
|---|---|
| **파일** | `config/commodity_mapping.json` (백엔드 루트) |
| **발견 경로** | 파이프라인 통합 검증 (2026-05-19) |
| **증상** | Phase 0 step2~5, collectors 실행 시 `FileNotFoundError: config/commodity_mapping.json` |
| **원인** | develop 브랜치의 `config/commodity_mapping.json` 이 backend root 레벨에 복사되지 않음. 6개 스크립트가 `PROJECT_ROOT/config/` 를 참조하지만 해당 경로에 파일 없음 |
| **수정** | `config/commodity_mapping.json` 을 backend root에 추가 + `data/raw/`, `data/processed/` 디렉토리 구조 생성 |
| **상태** | 수정완료 |

---
