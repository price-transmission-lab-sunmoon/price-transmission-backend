# 예외처리 코드 명세서 (v5)

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: 예외 코드 인덱스 — AI 코드 구현·디버깅 프롬프트 첨부용
**작성일**: 2026-04-28
**적용 범위**: 백엔드(FastAPI) + DB 적재 레이어 + 파싱 레이어 + 프론트엔드(React)
**변경 이력**:
- v1 → v2: 당시 pipeline_output_spec v5 반영. PL-P4-001 발생 위치 수정.
- v2 → v3: 문서 분리. 설계 정보를 당시 exception_design v1 파일로 이관.
- v3 → v4: **계량경제학 파이프라인(PL-*) 전체 제거** — 파이프라인은 예외처리 대상 외. `PARSE-*` 도메인 신규 추가(프레임워크 간 데이터 파싱). `FE-*` 도메인 신규 추가(프론트엔드 React). 기능 개발 브랜치(당시 feature_dev_list v2) 기준 기능별 예외처리 매핑 추가. 에러 체이닝 예상 출력문 추가.
- v4 → v5 (2026-05-02): 본문 정정. `reference_audit_report v1` §4 규칙에 따라 외부 참조 표기를 `abcd_vN.md`로 일괄 전환. 구버전 참조(당시 exception_design v1, feature_dev_list v2) 전부 정정. 본 문서는 이제 `docs/docs_manifest.md`의 버전 해석기에 의해 자동 최신 참조되며, 파일명·본문은 `_v5`로 정합.

> **관련 문서**: 에러 체이닝 구현 설계 및 상관관계 매트릭스 → `exception_design_vN.md`

---

## 1. 사용 규칙 (AI·사람 공통)

### 1.1 목적

런타임 오류 발생 시 로그에 기록된 **에러 코드** 하나로 오류 발생 지점·원인·권장 처리 방침을 특정한다. 코드 전수 조사 없이 본 문서만 조회하여 판단한다.

### 1.2 코드 포맷

```
{도메인}-{계층}-{순번}
```

| 도메인 | 의미 | 예시 |
|---|---|---|
| `DB` | DB 적재 / ORM 레이어 | `DB-CONN-001` |
| `API` | FastAPI 엔드포인트 / 응답 계층 | `API-STR-001` |
| `PARSE` | 프레임워크 간 데이터 파싱 레이어 | `PARSE-DATE-001` |
| `FE` | 프론트엔드 React 레이어 | `FE-API-001` |
| `CFG` | 설정 / 환경 변수 | `CFG-CORE-001` |
| `EXT` | 외부 API 호출 | `EXT-ECOS-001` |

> **파이프라인(PL-*)**: 계량경제학 파이프라인은 예외처리 대상 외. 파이프라인 코드에서는 Python 기본 예외를 그대로 허용하며 별도 에러 코드를 부여하지 않는다.

### 1.3 로깅 규칙

모든 예외는 아래 필드를 **반드시** 로그에 포함한다.

```python
# 백엔드 예시
raise APIError(
    code="API-COM-001",
    message="품목 미존재",
    context={"commodity_id": "wheat"},
    http_status=404,
    public_code="COMMODITY_NOT_FOUND",
) from e   # 반드시 from e 명시 — 생략 시 체인 추적 불가
```

```typescript
// 프론트엔드 예시
throw new FEError("FE-API-001", "API 응답 파싱 실패", {
  endpoint: "/commodities/wheat/stream",
  status: 200,
  field: "data.points[0].period",
});
```

- 로그 한 줄에 **code**가 반드시 나타나야 한다.
- `context`는 원인 추적에 필요한 입력값 + 상태값. 민감 정보 포함 금지.
- `raise X from e` 컨벤션을 반드시 지킨다. `from None` 사용 금지.

### 1.4 AI 사용 규칙

- 예외 클래스를 새로 정의할 때 반드시 §2 인덱스에 있는 코드 중 하나를 사용한다.
- 해당하는 코드가 없으면 §8 신규 추가 규칙에 따라 `(proposed)` 상태로 제안한다.
- 로그 메시지는 한국어, 코드·키는 영문 고정.
- 디버깅 시 ORIGIN 에러 코드 + context 스냅샷을 함께 제시한다. 체인 추적 구현은 `exception_design_vN.md` 참조.

### 1.5 처리 방침 종류

| 방침 | 의미 | 후속 |
|---|---|---|
| **FATAL** | 서버 기동 중단 또는 배치 실행 전체 중단 | 수동 개입 필요 |
| **RETRY** | 재시도 후 최종 실패 시 FATAL 또는 SKIP | 지수 백오프 |
| **WARN** | 진행하되 경고 기록 | 내부 로그 |
| **CLIENT_400** | API 400 응답 | `error.code` 본문 노출 |
| **CLIENT_404** | API 404 응답 | `error.code` 본문 노출 |
| **CLIENT_429** | API 429 응답 | Rate limit |
| **CLIENT_500** | API 500 응답 | 내부 코드 노출 금지, 내부 로그만 |
| **FE_FALLBACK** | 프론트엔드 — 폴백 UI 표시 | 에러 바운더리 또는 빈 상태 |
| **FE_TOAST** | 프론트엔드 — 토스트 메시지 표시 후 계속 | 비차단 |
| **FE_BLOCK** | 프론트엔드 — 해당 뷰 렌더링 차단 | 에러 UI 대체 |

---

## 2. 전체 인덱스 (빠른 조회용)

### 2.1 DB 적재 레이어

| 코드 | 발생 위치 | 원인 요약 | 처리 방침 |
|---|---|---|---|
| [DB-CONN-001](#db-conn-001) | 커넥션 | DB 연결 실패 | FATAL |
| [DB-CONN-002](#db-conn-002) | 커넥션 | 풀 고갈 | RETRY 3회 |
| [DB-TX-001](#db-tx-001) | 트랜잭션 | Phase 적재 중 실패 | 해당 Phase 롤백 |
| [DB-UNIQ-001](#db-uniq-001) | 적재 | `raw_prices` UNIQUE 위반 | UPSERT |
| [DB-UNIQ-002](#db-uniq-002) | 적재 | `anomaly_results` UNIQUE 위반 | UPSERT |
| [DB-UNIQ-003](#db-uniq-003) | 적재 | `stat_timeseries` UNIQUE 위반 | UPSERT |
| [DB-FK-001](#db-fk-001) | 적재 | `commodity_id` 미존재 | FATAL |
| [DB-FK-002](#db-fk-002) | 적재 | `segment_id` 미존재 | FATAL |
| [DB-FK-003](#db-fk-003) | 적재 | `subperiod_id` 참조 오류 | WARN (NULL 적재) |
| [DB-TYPE-001](#db-type-001) | 적재 | `period`가 월초가 아님 | FATAL |
| [DB-TYPE-002](#db-type-002) | 적재 | `NUMERIC` 자릿수 초과 | FATAL |
| [DB-NN-001](#db-nn-001) | 적재 | NOT NULL 위반 (`confidence_grade`) | FATAL |
| [DB-NN-002](#db-nn-002) | 적재 | NOT NULL 위반 (`primary_pattern`) | FATAL |
| [DB-ARR-001](#db-arr-001) | 적재 | `pattern_types` 빈 배열 | FATAL |
| [DB-ARR-002](#db-arr-002) | 적재 | `bp_dates` 파싱 실패 | WARN (NULL 적재) |
| [DB-RUN-001](#db-run-001) | 배치 | `pipeline_runs` 중복 생성 | FATAL |
| [DB-CACHE-001](#db-cache-001) | Redis | Redis 연결 실패 | WARN (캐시 없이 DB 직접 조회) |
| [DB-CACHE-002](#db-cache-002) | Redis | 캐시 직렬화/역직렬화 실패 | WARN (캐시 skip, DB 조회) |

### 2.2 API 레이어 (FastAPI)

| 코드 | 엔드포인트 | 원인 요약 | HTTP |
|---|---|---|---|
| [API-COM-001](#api-com-001) | `/commodities/{id}` | 품목 미존재 | 404 `COMMODITY_NOT_FOUND` |
| [API-COM-002](#api-com-002) | 참조류 | Phase 0 미완 | 500 `PIPELINE_DATA_MISSING` |
| [API-ANO-001](#api-ano-001) | `/anomalies/{id}/*` | anomaly_id 미존재 | 404 `ANOMALY_NOT_FOUND` |
| [API-ANO-002](#api-ano-002) | `/anomalies/{id}/detail` | 연관 stat 행 없음 | 500 `PIPELINE_DATA_MISSING` |
| [API-ANO-003](#api-ano-003) | `/anomalies/{id}/ml-map` | ML 투영 미산출 | 404 `ML_MAP_NOT_READY` |
| [API-STR-001](#api-str-001) | 시계열류 | 전체 범위가 warmup 내 | 404 `WARMUP_PERIOD_ONLY` |
| [API-STR-002](#api-str-002) | 시계열류 | `from > to` | 400 `INVALID_DATE_RANGE` |
| [API-STR-003](#api-str-003) | 시계열류 | 분석 가용 범위 완전 이탈 | 400 `INVALID_DATE_RANGE` |
| [API-STR-004](#api-str-004) | 시계열류 | `granularity` 비허용 값 | 400 `INVALID_GRANULARITY` |
| [API-STR-005](#api-str-005) | `/scatter` | `until > to` | 400 `UNTIL_EXCEEDS_TO` |
| [API-SEG-001](#api-seg-001) | 구간 지정류 | 품목에 없는 구간 요청 | 400 `INVALID_SEGMENT` |
| [API-LAY-001](#api-lay-001) | `/raw-prices` | `layout` 범위 밖 | 400 `INVALID_LAYOUT` |
| [API-LAY-002](#api-lay-002) | `/raw-prices` | 3구간 품목에 레이아웃 4 요청 | 400 `WHOLESALE_NOT_AVAILABLE` |
| [API-MET-001](#api-met-001) | `/stat-series` | 비허용 metric | 400 `INVALID_METRIC` |
| [API-MET-002](#api-met-002) | `/stat-series` | 스냅샷 전용 metric 요청 | 400 `SNAPSHOT_METRIC_ON_SERIES` |
| [API-MET-003](#api-met-003) | `/stat-snapshot` | 비허용 metric | 400 `INVALID_METRIC` |
| [API-VAL-001](#api-val-001) | 전체 | Pydantic 검증 실패 | 400 |
| [API-RATE-001](#api-rate-001) | 전체 | Rate limit 초과 | 429 |
| [API-INT-001](#api-int-001) | 전체 | 내부 미매핑 예외 | 500 `INTERNAL_ERROR` |
| [API-BATCH-001](#api-batch-001) | 배치 스케줄러 | 배치 실행 중 예외 | WARN (로그만, 서버 유지) |
| [API-BATCH-002](#api-batch-002) | 배치 스케줄러 | 배치 중복 실행 감지 | WARN (실행 skip) |

### 2.3 파싱 레이어 (PARSE)

> 파이프라인(Python) → DB(PostgreSQL) → API(FastAPI) → 프론트엔드(React) 간  
> 데이터 변환·파싱 과정에서 발생하는 예외. 프레임워크 경계마다 별도 검증이 필요하다.

| 코드 | 발생 위치 | 원인 요약 | 처리 방침 |
|---|---|---|---|
| [PARSE-DATE-001](#parse-date-001) | DB→API Pydantic | `DATE` → `YYYY-MM` 변환 실패 | CLIENT_500 |
| [PARSE-DATE-002](#parse-date-002) | API→FE | API 응답 `YYYY-MM` 파싱 실패 (프론트) | FE_FALLBACK |
| [PARSE-NUM-001](#parse-num-001) | DB→API | `NUMERIC` → `float` 오버플로우 | CLIENT_500 |
| [PARSE-NUM-002](#parse-num-002) | API→FE | API 숫자 필드가 `null` / `NaN` 문자열 | FE_FALLBACK |
| [PARSE-ARR-001](#parse-arr-001) | DB→API | `VARCHAR[]` → Python list 변환 실패 | CLIENT_500 |
| [PARSE-ARR-002](#parse-arr-002) | API→FE | 배열 응답에서 예상 필드 누락 | FE_FALLBACK |
| [PARSE-ENUM-001](#parse-enum-001) | DB→API | DB 열거형 값이 Pydantic Enum 외 | CLIENT_500 |
| [PARSE-ENUM-002](#parse-enum-002) | API→FE | API 문자열이 TypeScript union 외 | FE_TOAST |
| [PARSE-SCHEMA-001](#parse-schema-001) | API→FE | 응답 최상위 envelope 구조 불일치 | FE_BLOCK |
| [PARSE-REDIS-001](#parse-redis-001) | Redis→API | Redis JSON 역직렬화 실패 | WARN (캐시 skip) |

### 2.4 프론트엔드 (FE)

| 코드 | 발생 위치 | 원인 요약 | 처리 방침 |
|---|---|---|---|
| [FE-API-001](#fe-api-001) | React Query | API 요청 네트워크 실패 | FE_TOAST + 재시도 버튼 |
| [FE-API-002](#fe-api-002) | React Query | API 400 응답 | FE_TOAST (사용자 입력 오류 안내) |
| [FE-API-003](#fe-api-003) | React Query | API 404 응답 | FE_FALLBACK (빈 상태 UI) |
| [FE-API-004](#fe-api-004) | React Query | API 500 응답 | FE_BLOCK (에러 UI) |
| [FE-API-005](#fe-api-005) | React Query | 응답 타임아웃 | FE_TOAST + 재시도 버튼 |
| [FE-D3-001](#fe-d3-001) | D3.js 렌더링 | 데이터 빈 배열 (points: []) | FE_FALLBACK (빈 차트) |
| [FE-D3-002](#fe-d3-002) | D3.js 렌더링 | 스케일 계산 오류 (NaN 포함 데이터) | FE_FALLBACK |
| [FE-D3-003](#fe-d3-003) | D3.js 렌더링 | SVG 컨테이너 크기 0 | FE_FALLBACK |
| [FE-STORE-001](#fe-store-001) | Zustand store | 상태 hydration 실패 | FE_FALLBACK (초기 상태로 복구) |
| [FE-STORE-002](#fe-store-002) | Zustand store | 선택 품목과 API 응답 품목 불일치 | FE_TOAST |
| [FE-MOCK-001](#fe-mock-001) | Mock 모드 | `VITE_USE_MOCK=true` 상태에서 fixture 파일 없음 | FE_BLOCK (개발환경 전용) |

### 2.5 설정 / 외부 API

| 코드 | 발생 위치 | 원인 요약 | 처리 방침 |
|---|---|---|---|
| [CFG-CORE-001](#cfg-core-001) | 부팅 | 필수 환경 변수 누락 | FATAL |
| [CFG-CORE-002](#cfg-core-002) | 부팅 | `product_config.json` 스키마 오류 | FATAL |
| [CFG-CORE-003](#cfg-core-003) | 부팅 | `settings.py` 파라미터 범위 위반 | FATAL |
| [EXT-PINK-001](#ext-pink-001) | World Bank Pink Sheet | 응답 비정상 | RETRY 3회 → SKIP |
| [EXT-FAO-001](#ext-fao-001) | FAO FFPI | 응답 비정상 | RETRY 3회 → SKIP |
| [EXT-CUST-001](#ext-cust-001) | 관세청 | 응답 비정상 | RETRY 3회 → SKIP |
| [EXT-ECOS-001](#ext-ecos-001) | 한국은행 ECOS | 응답 비정상 | RETRY 3회 → SKIP |
| [EXT-KAMIS-001](#ext-kamis-001) | KAMIS | 응답 비정상 | RETRY 3회 → SKIP |
| [EXT-FX-001](#ext-fx-001) | 환율 API | 응답 비정상 | RETRY 3회 → FATAL |

---

## 3. DB 적재 레이어 상세

### 커넥션 / 트랜잭션

#### DB-CONN-001
- **원인**: PostgreSQL 연결 실패.
- **context 필수**: `dsn_redacted`, `error_type`
- **방침**: FATAL. `pipeline_runs.status='failed'`.

#### DB-CONN-002
- **원인**: SQLAlchemy async pool 고갈.
- **context 필수**: `pool_size`, `active`, `queue_wait_ms`
- **방침**: RETRY 3회(지수 백오프 1s/2s/4s). 모두 실패 시 DB-CONN-001로 승격.

#### DB-TX-001
- **원인**: Phase 적재 중 예외 발생. ORM 세션 롤백.
- **context 필수**: `phase`, `commodity_id`, `failed_table`, `underlying_error_code`
- **방침**: 해당 Phase 전체 롤백. 다음 Phase 실행하지 않음. `pipeline_runs.phases_run`에 해당 Phase 미기록.

### 제약 위반

#### DB-UNIQ-001
- **원인**: `raw_prices (commodity_id, period)` UNIQUE 위반.
- **context 필수**: `commodity_id`, `period`, `pipeline_run_id`
- **방침**: UPSERT (`ON CONFLICT DO UPDATE`).

#### DB-UNIQ-002
- **원인**: `anomaly_results (commodity_id, segment_id, period, primary_pattern)` UNIQUE 위반.
- **context 필수**: `commodity_id`, `segment_id`, `period`, `primary_pattern`
- **방침**: UPSERT. 설계 문제점 D-13 결정 시 UNIQUE 키 재정의 필요.

#### DB-UNIQ-003
- **원인**: `stat_timeseries (commodity_id, segment_id, period)` UNIQUE 위반.
- **방침**: UPSERT.

### FK

#### DB-FK-001
- **원인**: `commodities`에 등록되지 않은 `commodity_id` 참조.
- **context 필수**: `table`, `commodity_id`
- **방침**: FATAL. 시드 적재 누락 의심. 재시드 후 재실행.

#### DB-FK-002
- **원인**: `segments`에 등록되지 않은 `segment_id` 참조.
- **방침**: FATAL.

#### DB-FK-003
- **원인**: `subperiod_id` 참조 대상 부재.
- **context 필수**: `table`, `commodity_id`, `segment_id`, `subperiod_id`
- **방침**: WARN. `NULL`로 적재. `subperiods` 적재 완료 후 후보정 배치.

### 타입 / 제약

#### DB-TYPE-001
- **원인**: `period` 값이 월초(`YYYY-MM-01`)가 아님.
- **context 필수**: `table`, `period_raw`
- **방침**: FATAL. 입력 정규화 레이어 버그. 설계 문제점 D-11.

#### DB-TYPE-002
- **원인**: `NUMERIC(precision, scale)` 자릿수 초과.
- **context 필수**: `table`, `column`, `value`
- **방침**: FATAL. 스키마 precision 재검토.

#### DB-NN-001
- **원인**: `anomaly_results.confidence_grade` NULL 시도.
- **context 필수**: `commodity_id`, `segment_id`, `period`
- **방침**: FATAL. 설계 문제점 D-02 직결. 적재 전 필터 규칙 재확인.

#### DB-NN-002
- **원인**: `primary_pattern` NULL 시도.
- **방침**: FATAL.

#### DB-ARR-001
- **원인**: `pattern_types` 빈 배열 `{}` 적재.
- **방침**: FATAL.

#### DB-ARR-002
- **원인**: `bp_dates` 파싱 실패(형식 불일치).
- **context 필수**: `commodity_id`, `segment_id`, `raw_value`
- **방침**: WARN. `NULL`로 적재. 설계 문제점 D-07.

### 배치 관리

#### DB-RUN-001
- **원인**: 동일 `run_date`로 `pipeline_runs` 중복 생성.
- **방침**: FATAL. 수동 개입 요구.

### Redis 캐시

#### DB-CACHE-001
- **원인**: Redis 연결 실패 (`feat/be-redis` 적용 후).
- **context 필수**: `redis_url_redacted`, `error_type`
- **방침**: WARN. 캐시 없이 DB 직접 조회. 서비스 중단 없음.
- **관련 기능**: `feat/be-redis`

#### DB-CACHE-002
- **원인**: Redis에서 꺼낸 값의 JSON 역직렬화 실패. 스키마 변경 후 구 캐시가 남아있을 때 발생.
- **context 필수**: `cache_key`, `raw_value_preview`
- **방침**: WARN. 해당 캐시 키 삭제 후 DB 재조회. `PARSE-REDIS-001`과 구분 — 이쪽은 Redis 레이어, PARSE-REDIS-001은 API 레이어에서 감지.
- **관련 기능**: `feat/be-redis`

---

## 4. API 레이어 상세 (FastAPI)

공통: 응답 envelope는 `{"error": {"code": "...", "message": "..."}}`. 디버깅 컨텍스트는 내부 로그에만 기록.

### 참조 / 탐지 ID

#### API-COM-001
- **엔드포인트**: `/commodities/{id}`, `/commodities/{id}/*`
- **원인**: DB `commodities.commodity_id` 미존재.
- **HTTP**: 404 `COMMODITY_NOT_FOUND`
- **사용자 메시지**: "요청한 품목을 찾을 수 없습니다."
- **관련 기능**: `feat/be-api-reference`

#### API-COM-002
- **엔드포인트**: 참조/시각화 엔드포인트 전반
- **원인**: 품목은 있으나 `analysis_start`가 NULL (Phase 0 미완).
- **HTTP**: 500 `PIPELINE_DATA_MISSING`
- **관련 기능**: `feat/be-api-reference`, `feat/be-api-timeseries`

#### API-ANO-001
- **엔드포인트**: `/anomalies/{anomaly_id}/*` 전체
- **원인**: `anomaly_results.id` 미존재.
- **HTTP**: 404 `ANOMALY_NOT_FOUND`
- **관련 기능**: `feat/be-api-anomaly`, `feat/be-api-panel`

#### API-ANO-002
- **엔드포인트**: `/anomalies/{id}/detail`, `/stat-series`, `/stat-snapshot`
- **원인**: anomaly_id는 있으나 관련 `stat_timeseries`/`baselines` 행 없음.
- **HTTP**: 500 `PIPELINE_DATA_MISSING`
- **관련 기능**: `feat/be-api-panel`

#### API-ANO-003
- **엔드포인트**: `/anomalies/{id}/ml-map`
- **원인**: `ml_projections` 미산출.
- **HTTP**: 404 `ML_MAP_NOT_READY`
- **관련 기능**: `feat/be-api-panel`

### 쿼리 파라미터

#### API-STR-001
- **엔드포인트**: 시계열류 전반
- **원인**: 요청 범위 전체가 warmup 기간 내.
- **HTTP**: 404 `WARMUP_PERIOD_ONLY`
- **사용자 메시지**: "요청한 기간은 분석 기준 분포 축적 기간입니다."
- **관련 기능**: `feat/be-api-timeseries`

#### API-STR-002
- **원인**: `from > to`.
- **HTTP**: 400 `INVALID_DATE_RANGE`
- **관련 기능**: `feat/be-api-timeseries`, `feat/be-api-panel`

#### API-STR-003
- **원인**: `from`/`to`가 `analysis_start`~`analysis_end` 완전 이탈. 클램핑 대상 범위 이탈.
- **HTTP**: 400 `INVALID_DATE_RANGE`
- **구현 주의**: 부분 이탈은 클램핑 후 `actual_from`/`actual_to` echo. 완전 이탈에만 이 코드.
- **관련 기능**: `feat/be-api-timeseries`

#### API-STR-004
- **원인**: `granularity` 값이 `monthly`/`quarterly`/`yearly` 외.
- **HTTP**: 400 `INVALID_GRANULARITY`
- **관련 기능**: `feat/be-api-timeseries`

#### API-STR-005
- **엔드포인트**: `/scatter`
- **원인**: `until > to`.
- **HTTP**: 400 `UNTIL_EXCEEDS_TO`
- **관련 기능**: `feat/be-api-timeseries`

### 구간 / 레이아웃 / 메트릭

#### API-SEG-001
- **원인**: 품목의 `segments`에 없는 구간 요청.
- **HTTP**: 400 `INVALID_SEGMENT`
- **관련 기능**: `feat/be-api-timeseries`, `feat/be-api-panel`

#### API-LAY-001
- **원인**: `/raw-prices`의 `layout`이 1~6 밖.
- **HTTP**: 400 `INVALID_LAYOUT`
- **관련 기능**: `feat/be-api-timeseries`

#### API-LAY-002
- **원인**: 3구간 품목에 레이아웃 4(도매가 포함) 요청.
- **HTTP**: 400 `WHOLESALE_NOT_AVAILABLE`
- **주의**: 레이아웃 5(PPI-CPI)는 3구간 품목에서 자동 폴백(에러 아님). 레이아웃 4만 이 코드.
- **관련 기능**: `feat/be-api-timeseries`

#### API-MET-001
- **엔드포인트**: `/stat-series`
- **원인**: `metric`이 허용 목록(`transmission_rate`/`zscore`/`ect`/`spread`) 밖.
- **HTTP**: 400 `INVALID_METRIC`
- **관련 기능**: `feat/be-api-panel`

#### API-MET-002
- **엔드포인트**: `/stat-series`
- **원인**: `metric=iqr` 또는 `metric=asymmetry`(스냅샷 전용).
- **HTTP**: 400 `SNAPSHOT_METRIC_ON_SERIES`
- **사용자 메시지**: "해당 지표는 `/anomalies/{id}/stat-snapshot` 엔드포인트를 사용하십시오."
- **관련 기능**: `feat/be-api-panel`

#### API-MET-003
- **엔드포인트**: `/stat-snapshot`
- **원인**: `metric`이 `iqr`/`asymmetry` 밖.
- **HTTP**: 400 `INVALID_METRIC`
- **관련 기능**: `feat/be-api-panel`

### 공통

#### API-VAL-001
- **원인**: Pydantic 검증 실패(타입·필수값).
- **HTTP**: 400. `context`에 `loc`, `input`.

#### API-RATE-001
- **원인**: Rate limit 초과 (1차 출시 범위 외, 슬롯 선점).
- **HTTP**: 429.

#### API-INT-001
- **원인**: 내부 예외 중 핸들러 미매핑.
- **HTTP**: 500 `INTERNAL_ERROR`
- **주의**: 사용자에게 내부 코드 노출 금지. 내부 로그에만 상세 기록.

### 배치 스케줄러

#### API-BATCH-001
- **원인**: APScheduler 월별 배치 실행 중 예외 발생.
- **context 필수**: `run_date`, `stage`, `underlying_error`
- **방침**: WARN. `pipeline_runs.status='failed'` 기록. 서버는 유지. 다음 배치까지 대기.
- **관련 기능**: `feat/be-batch`

#### API-BATCH-002
- **원인**: 동일 `run_date`에 배치 중복 실행 감지 (락 확인 실패).
- **context 필수**: `run_date`, `existing_run_id`
- **방침**: WARN. 실행 skip. 기존 실행 완료까지 대기.
- **관련 기능**: `feat/be-batch`

---

## 5. 파싱 레이어 상세 (PARSE)

> 프레임워크 경계에서 발생하는 타입 변환·형식 불일치 예외.  
> 각 경계마다 Pydantic(백엔드) 또는 Zod/타입 가드(프론트엔드)로 명시적 검증이 필요하다.

### 날짜 / 기간

#### PARSE-DATE-001
- **경계**: DB(`DATE`) → API(Pydantic serializer) → `YYYY-MM` 문자열 변환 실패.
- **원인**: DB에 `NULL` 또는 비정상 날짜 값이 있을 때. 정규화 레이어 버그.
- **context 필수**: `table`, `column`, `raw_value`
- **방침**: CLIENT_500. 내부 로그에 상세 기록.
- **관련 기능**: `feat/be-db-pipeline`, `feat/be-api-reference`

#### PARSE-DATE-002
- **경계**: API 응답(`YYYY-MM`) → 프론트엔드 Date 객체 파싱 실패.
- **원인**: API 응답 형식이 `YYYY-MM`이 아닌 값일 때 (예: `null`, 빈 문자열, ISO 8601 전체).
- **context 필수**: `endpoint`, `field`, `raw_value`
- **방침**: FE_FALLBACK. 해당 포인트는 빈 값으로 표시. 콘솔 경고.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-raw-timeseries`

### 숫자

#### PARSE-NUM-001
- **경계**: DB(`NUMERIC`) → Python `float` 변환 오버플로우.
- **context 필수**: `table`, `column`, `value`
- **방침**: CLIENT_500.

#### PARSE-NUM-002
- **경계**: API 숫자 필드가 `null` 또는 `"NaN"` 문자열로 응답됨.
- **원인**: 파이프라인 계산 결과 NaN이 DB에 저장됐거나, Pydantic이 NaN을 직렬화할 때 발생.
- **context 필수**: `endpoint`, `field`
- **방침**: FE_FALLBACK. 해당 필드 값을 `—` 또는 `N/A`로 표시. 차트 데이터인 경우 해당 포인트 skip.
- **관련 기능**: `feat/fe-panel`, `feat/fe-stream-chart`

### 배열

#### PARSE-ARR-001
- **경계**: DB(`VARCHAR[]`) → Python list 변환 실패.
- **context 필수**: `table`, `column`, `raw_value`
- **방침**: CLIENT_500.

#### PARSE-ARR-002
- **경계**: API 배열 응답에서 필수 필드 누락 (예: `points` 배열의 각 요소에서 `period` 키 없음).
- **context 필수**: `endpoint`, `field`, `index`
- **방침**: FE_FALLBACK. 해당 배열 전체를 빈 상태로 처리. 콘솔 경고.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-panel`

### 열거형

#### PARSE-ENUM-001
- **경계**: DB 열거형 값이 Pydantic `Literal` / `Enum` 정의 밖.
- **원인**: DB에 레거시 값 또는 오타가 있을 때.
- **context 필수**: `table`, `column`, `value`, `allowed_values`
- **방침**: CLIENT_500.

#### PARSE-ENUM-002
- **경계**: API 문자열 필드 값이 TypeScript union 타입 정의 밖.
- **원인**: 백엔드에서 새 열거형 값이 추가됐으나 프론트 타입 정의가 미갱신.
- **context 필수**: `field`, `value`
- **방침**: FE_TOAST. "지원되지 않는 데이터 형식입니다." 표시. 기본값으로 폴백.
- **관련 기능**: `feat/fe-api-connect`

### 응답 구조

#### PARSE-SCHEMA-001
- **경계**: API 응답 최상위 envelope 구조 불일치.
- **원인**: 백엔드 응답 envelope가 `{"data": ..., "meta": ...}` 형식에서 벗어난 경우.
- **context 필수**: `endpoint`, `received_keys`
- **방침**: FE_BLOCK. 해당 뷰 에러 UI 표시.
- **관련 기능**: `feat/fe-api-connect`

### Redis 역직렬화

#### PARSE-REDIS-001
- **경계**: Redis 캐시 → API 응답 조립 시 JSON 역직렬화 실패.
- **원인**: 캐시된 JSON이 현재 Pydantic 스키마와 불일치 (배포 후 구 캐시).
- **context 필수**: `cache_key`, `error_msg`
- **방침**: WARN. 해당 캐시 무효화 후 DB 재조회. `DB-CACHE-002`와 구분 — 이 코드는 API 레이어에서 Pydantic 검증 중 감지.
- **관련 기능**: `feat/be-redis`

---

## 6. 프론트엔드 상세 (FE)

> 프론트엔드 예외는 콘솔 에러 출력 + Sentry 등 모니터링 툴 연동을 기준으로 설계한다.  
> 사용자에게는 에러 코드를 노출하지 않고 처리 방침에 따른 UI 상태만 표시한다.

### API 통신

#### FE-API-001
- **원인**: React Query 요청 중 네트워크 실패 (fetch error, CORS, 서버 다운).
- **context 필수**: `endpoint`, `error_type`
- **방침**: FE_TOAST ("데이터를 불러오지 못했습니다.") + 재시도 버튼. React Query `retry: 3` 설정.
- **관련 기능**: `feat/fe-api-connect`

#### FE-API-002
- **원인**: API 400 응답. 잘못된 쿼리 파라미터 등 사용자 입력 오류.
- **context 필수**: `endpoint`, `api_error_code`, `message`
- **방침**: FE_TOAST. `error.code`에 따라 사용자 친화 메시지 매핑.
- **관련 기능**: `feat/fe-layout-filter`, `feat/fe-raw-timeseries`

#### FE-API-003
- **원인**: API 404 응답 (`COMMODITY_NOT_FOUND`, `ANOMALY_NOT_FOUND` 등).
- **context 필수**: `endpoint`, `api_error_code`
- **방침**: FE_FALLBACK. 빈 상태 UI("데이터가 없습니다.") 표시.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-panel`

#### FE-API-004
- **원인**: API 500 응답 (`PIPELINE_DATA_MISSING`, `INTERNAL_ERROR` 등).
- **context 필수**: `endpoint`, `api_error_code`
- **방침**: FE_BLOCK. 해당 컴포넌트 에러 UI 표시. 에러 바운더리로 전파 방지.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-panel`

#### FE-API-005
- **원인**: 응답 타임아웃 (기본 30초 초과).
- **context 필수**: `endpoint`, `elapsed_ms`
- **방침**: FE_TOAST ("응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.") + 재시도 버튼.
- **관련 기능**: `feat/fe-api-connect`

### D3.js 렌더링

#### FE-D3-001
- **원인**: API 응답 `points: []` (데이터 없음).
- **방침**: FE_FALLBACK. 빈 차트 상태 UI("해당 기간 데이터가 없습니다.") 표시.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-scatter-chart`, `feat/fe-raw-timeseries`

#### FE-D3-002
- **원인**: D3 스케일 계산 중 NaN 포함 데이터로 영역/축 계산 실패.
- **context 필수**: `chart_type`, `nan_field`, `count`
- **방침**: FE_FALLBACK. NaN 포인트 필터링 후 재렌더링. 필터링 후에도 실패하면 빈 차트.
- **관련 기능**: `feat/fe-stream-chart`, `feat/fe-panel`

#### FE-D3-003
- **원인**: SVG 컨테이너 `getBoundingClientRect()` 결과 width 또는 height가 0.
- **원인 배경**: 숨겨진 탭, 패널 애니메이션 완료 전 렌더링 시도.
- **방침**: FE_FALLBACK. `ResizeObserver`로 컨테이너 크기 복구 후 재렌더링.
- **관련 기능**: `feat/fe-panel`, `feat/fe-minimap`

### Zustand store

#### FE-STORE-001
- **원인**: store 초기 hydration 중 예상치 못한 타입 불일치.
- **방침**: FE_FALLBACK. 초기 상태(`initialState`)로 강제 복구.
- **관련 기능**: `feat/fe-layout-filter`

#### FE-STORE-002
- **원인**: Zustand에 저장된 `selectedCommodityId`로 API 조회 시 404 응답.
- **원인 배경**: 품목 목록이 갱신되어 이전 품목이 삭제된 경우.
- **방침**: FE_TOAST. 선택 품목 초기화 + 전체 품목 목록 최상단 품목으로 재선택.
- **관련 기능**: `feat/fe-layout-filter`

### Mock 모드 (개발환경 전용)

#### FE-MOCK-001
- **원인**: `VITE_USE_MOCK=true` 상태에서 요청된 fixture 파일이 `src/__fixtures__/`에 없음.
- **context 필수**: `fixture_path`
- **방침**: FE_BLOCK. **개발환경 전용 에러**. 프로덕션에서는 발생하지 않음.
- **관련 기능**: 전 FE 브랜치 (더미 데이터 단계)

---

## 7. 설정 / 외부 API 상세

### 설정

#### CFG-CORE-001
- **원인**: 필수 환경 변수 누락 (`DATABASE_URL`, `REDIS_URL` 등).
- **방침**: FATAL. 부팅 중단.

#### CFG-CORE-002
- **원인**: `product_config.json` 스키마 오류.
- **방침**: FATAL.

#### CFG-CORE-003
- **원인**: `settings.py` 값 범위 위반 (예: `ROLLING_WINDOW=0`, `CONTAMINATION>1`).
- **방침**: FATAL.

### 외부 API 공통

- 공통 재시도 정책: **3회 지수 백오프(1s, 2s, 4s)**.
- 환율(`EXT-FX-001`)만 최종 실패 시 **FATAL**.
- `context` 필수: `url_redacted`, `http_status`, `retry_count`, `elapsed_ms`.

#### EXT-PINK-001 / EXT-FAO-001 / EXT-CUST-001 / EXT-ECOS-001 / EXT-KAMIS-001
- **원인**: 해당 공공 데이터 소스 응답 비정상.
- **방침**: RETRY 3회 → SKIP.

#### EXT-FX-001
- **원인**: 환율 API 응답 비정상.
- **방침**: RETRY 3회 → FATAL.

---

## 8. 기능별 예외처리 매핑

> feature_dev_list_vN.md 기준 브랜치별로 구현해야 할 예외 코드를 발췌한다.  
> Feature 명세 §5 작성 시 이 표를 참조한다.

| 브랜치 | 구현 필수 예외 코드 |
|--------|-------------------|
| `feat/be-api-reference` | `API-COM-001`, `API-COM-002`, `API-VAL-001`, `API-INT-001`, `CFG-CORE-001`, `DB-CONN-001` |
| `feat/be-api-anomaly` | `API-ANO-001`, `API-INT-001` |
| `feat/be-api-timeseries` | `API-COM-001`, `API-STR-001~005`, `API-SEG-001`, `API-LAY-001~002`, `API-INT-001`, `PARSE-DATE-001`, `PARSE-NUM-001` |
| `feat/be-api-panel` | `API-ANO-001~003`, `API-MET-001~003`, `API-SEG-001`, `API-INT-001` |
| `feat/be-api-meta` | `API-INT-001` (정적 응답이므로 최소) |
| `feat/be-db-pipeline` | `DB-CONN-001~002`, `DB-TX-001`, `DB-UNIQ-001~003`, `DB-FK-001~003`, `DB-TYPE-001~002`, `DB-NN-001~002`, `DB-ARR-001~002`, `DB-RUN-001`, `PARSE-DATE-001`, `PARSE-ARR-001`, `PARSE-ENUM-001` |
| `feat/be-batch` | `API-BATCH-001~002`, `DB-RUN-001` |
| `feat/be-redis` | `DB-CACHE-001~002`, `PARSE-REDIS-001` |
| `feat/fe-layout-filter` | `FE-API-001~002`, `FE-STORE-001~002`, `FE-MOCK-001` |
| `feat/fe-stream-chart` | `FE-API-001~004`, `FE-D3-001~003`, `PARSE-DATE-002`, `PARSE-NUM-002`, `PARSE-ARR-002`, `FE-MOCK-001` |
| `feat/fe-minimap` | `FE-D3-001`, `FE-D3-003` |
| `feat/fe-panel` | `FE-API-001~004`, `FE-D3-001~003`, `PARSE-NUM-002`, `PARSE-ARR-002`, `FE-MOCK-001` |
| `feat/fe-scatter-chart` | `FE-API-001~004`, `FE-D3-001~002`, `PARSE-NUM-002` |
| `feat/fe-raw-timeseries` | `FE-API-001~004`, `FE-D3-001~003`, `PARSE-DATE-002`, `PARSE-NUM-002` |
| `feat/fe-methodology-tab` | `FE-API-001`, `FE-API-004` |
| `feat/fe-onboarding` | `FE-STORE-001` |
| `feat/fe-api-connect` | `FE-API-001~005`, `PARSE-SCHEMA-001`, `PARSE-ENUM-002` |

---

## 9. 에러 체이닝 예상 출력문

> 에러 체이닝 구현 상세 → `exception_design_vN.md` §2  
> 아래는 실제 런타임에서 `global_error_handler()` 출력이 어떻게 보일지 시나리오별 예시다.

### 시나리오 A — DB 연결 실패 → API 응답 실패

**발생 흐름**: PostgreSQL pool 고갈 → DB-CONN-002 → 재시도 실패 → DB-CONN-001 → API 500

```
============================================================
[ 에러 발생 ]
============================================================
ORIGIN  [DB-CONN-002] SQLAlchemy async pool 고갈 | context: {pool_size=10, active=10, queue_wait_ms=5023}
        └─ [DB-CONN-001] PostgreSQL 연결 실패
              └─ [API-INT-001] 내부 예외 처리 실패
============================================================
ORIGIN 코드: DB-CONN-002
============================================================
```

**사용자에게 반환되는 API 응답 (500)**:
```json
{"error": {"code": "INTERNAL_ERROR", "message": "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}}
```

---

### 시나리오 B — Redis 역직렬화 실패 → DB 폴백 조회

**발생 흐름**: 배포 후 구 캐시 → PARSE-REDIS-001 → 경고 후 DB 재조회 성공

```
============================================================
[ 경고 ]
============================================================
ORIGIN  [PARSE-REDIS-001] Redis 캐시 JSON 역직렬화 실패 | context: {cache_key='stream:wheat:2020-01:2024-12', error_msg='ValidationError: field transmission_rate missing'}
============================================================
ORIGIN 코드: PARSE-REDIS-001
→ 조치: 캐시 키 삭제 후 DB 재조회. 200 응답 정상 반환.
============================================================
```

---

### 시나리오 C — 날짜 파싱 실패 → 500 응답

**발생 흐름**: DB에 비정상 날짜 저장 → PARSE-DATE-001 → API 500

```
============================================================
[ 에러 발생 ]
============================================================
ORIGIN  [PARSE-DATE-001] DB DATE → YYYY-MM 변환 실패 | context: {table='stat_timeseries', column='period', raw_value='0000-00-00'}
        └─ [API-INT-001] 내부 예외 처리 실패
============================================================
ORIGIN 코드: PARSE-DATE-001
============================================================
```

---

### 시나리오 D — 프론트엔드 D3 렌더링 실패 → 폴백 UI

**발생 흐름**: API 응답에 NaN 포함 → PARSE-NUM-002 → FE-D3-002

```
// 브라우저 콘솔 출력
[FE][PARSE-NUM-002] API 숫자 필드 null/NaN | {endpoint: '/commodities/wheat/stream', field: 'points[3].transmission_rate'}
[FE][FE-D3-002] D3 스케일 NaN 포함 | {chart_type: 'stream', nan_field: 'transmission_rate', count: 1}
→ 조치: NaN 포인트 1개 필터링 후 재렌더링 성공.
```

---

### 시나리오 E — 배치 실행 중단 → 서버 유지

**발생 흐름**: APScheduler 배치 중 DB 적재 실패 → API-BATCH-001

```
============================================================
[ 배치 경고 ]
============================================================
ORIGIN  [DB-TX-001] Phase 적재 중 트랜잭션 실패 | context: {phase='anomaly_results', commodity_id='banana', failed_table='anomaly_results', underlying_error_code='DB-UNIQ-002'}
        └─ [API-BATCH-001] APScheduler 월별 배치 예외 | context: {run_date='2026-04-01', stage='db_load'}
============================================================
ORIGIN 코드: DB-TX-001
→ 조치: pipeline_runs.status='failed' 기록. 서버는 정상 유지. 다음 배치(2026-05-15)까지 대기.
============================================================
```

---

## 10. 신규 추가 규칙 (AI 프롬프트용)

### 10.1 판단 플로우

1. §2 인덱스를 전수 조사한다.
2. **의미가 90% 이상 겹치는 코드**가 있으면 재사용한다.
3. 유사 코드가 없으면 다음 번호를 사용한다.
4. 사람 리뷰 전까지 **`(proposed)`** 표식을 붙인다.

### 10.2 제안 포맷

```markdown
### PARSE-DATE-003 (proposed)
- 원인: [1~2줄 요약]
- 경계 / context 필수: [경계 정보 + 키 목록]
- 방침: [처리 방침]
- 추가 근거: [기존 코드를 재사용하지 않은 이유]
```

### 10.3 금지 사항

- 코드 포맷 외 형식 사용 금지.
- 파이프라인(PL-*) 도메인 코드 신규 생성 금지 — 파이프라인은 예외처리 대상 외.
- 한 코드에 복수 처리 방침 금지.
- HTTP 4xx/5xx를 API 외 레이어에서 사용 금지.

---

## 11. 빠른 조회 팁

- **API 400/404/500 원인**: §2.2 인덱스 HTTP 컬럼 + `error.code` 필터.
- **프론트엔드 렌더링 멈춤**: FE-D3-001~003 → FE-API-003~004 순으로 확인.
- **파싱 오류 발생 경계 파악**: `PARSE-*` 코드의 "경계" 항목 확인.
- **Redis 캐시 의심**: `DB-CACHE-001~002` → `PARSE-REDIS-001` 순으로 확인.
- **배치 실패 후 서버 상태**: `API-BATCH-001~002` — 서버는 유지됨.
- **ORIGIN 에러 코드와 context 스냅샷 확인**: `exception_design_vN.md` §2 참조.

---

## 부록 A. 예외 클래스 계층 (구현 참조)

### 백엔드 (Python)

```python
class ProjectError(Exception):
    def __init__(self, code: str, message: str, context: dict = None):
        self.code = code
        self.message = message
        self.context = context or {}
        super().__init__(f"[{code}] {message}")

class DBError(ProjectError):
    def __init__(self, code, message, context=None, table: str = None):
        super().__init__(code, message, context)
        self.table = table

class APIError(ProjectError):
    def __init__(self, code, message, context=None, http_status: int = 500, public_code: str = "INTERNAL_ERROR"):
        super().__init__(code, message, context)
        self.http_status = http_status
        self.public_code = public_code

class ParseError(ProjectError):
    def __init__(self, code, message, context=None, boundary: str = ""):
        super().__init__(code, message, context)
        self.boundary = boundary  # 예: "DB→API", "API→FE"

class ConfigError(ProjectError):
    pass

class ExternalAPIError(ProjectError):
    def __init__(self, code, message, context=None, source: str = "", retry_count: int = 0):
        super().__init__(code, message, context)
        self.source = source
        self.retry_count = retry_count
```

### 프론트엔드 (TypeScript)

```typescript
class FEError extends Error {
  code: string;
  context: Record<string, unknown>;

  constructor(code: string, message: string, context: Record<string, unknown> = {}) {
    super(`[${code}] ${message}`);
    this.code = code;
    this.context = context;
  }
}

// 사용 예시
throw new FEError("FE-D3-002", "D3 스케일 NaN 포함 데이터", {
  chart_type: "stream",
  nan_field: "transmission_rate",
  count: 1,
});
```

구조화 로그 한 줄 포맷 (백엔드):
```json
{"ts": "2026-04-28T09:32:11Z", "level": "ERROR", "code": "DB-CONN-002",
 "msg": "SQLAlchemy async pool 고갈", "context": {"pool_size": 10, "active": 10, "queue_wait_ms": 5023}}
```

에러 체이닝 구현(ORIGIN 추적 + context 스냅샷 출력) → `exception_design_vN.md` 참조.

---

*코드 구현 착수 시 이 문서를 프롬프트 첨부로 사용한다. 신규 상황 발생 시 §10 규칙에 따라 `(proposed)` 상태로 추가한 뒤 사람 리뷰로 확정한다.*
