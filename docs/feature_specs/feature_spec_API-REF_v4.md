# Feature 명세서 — 참조 엔드포인트 5개

**문서 유형**: Feature 명세서
**기능 번호**: `API-REF`
**브랜치명**: `feat/be-api-reference`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-04-30
**수정일**: 2026-05-11 (v4 — 참조 문서 버전 갱신 + `has_anomaly_this_month` 타입 수정)
**상태**: 초안

**변경 이력**:
- v1 (2026-04-30): 최초 작성.
- v2 (2026-05-01): db_schema v3→v4 교체, 데이터 흐름 보완, 처리 방침 표기 통일.
- v3 (2026-05-03): **중대 결함 수정** — 참조 문서 전체가 구버전(v4/v2)으로 고정되어 있던 오류 수정. `docs_manifest.md §1` 기준으로 `api_spec`·`db_schema`·`exception_spec` v4→v5, `exception_design`·`frame_spec_backend` v2→v3로 갱신. `abcd_vN.md` 표기 규칙으로 전환 (`reference_audit_report v1 §4` 정책 준수). `latest_anomaly_grade` Literal 타입 명시 (`string | null` → `"high" | "medium" | "reference" | null`). 문서 버전 재검증 체크리스트(§10) 신설.
- v4 (2026-05-11): 참조 문서 버전 갱신 — `exception_spec` v5→v6, `frame_spec_backend` v3→v4. 서비스 파일 참조 섹션 `§8.4 예외 클래스` 추가. `has_anomaly_this_month` 타입 `boolean | null` → `boolean` 수정 (`api_spec_vN §GET /commodities` non-nullable 정의 기준). `§10.1` 재검증 테이블 버전 동기화.

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.
>
> ⚠️ **버전 확인 의무**: 아래 "버전" 열은 `docs_manifest.md §1`에서 확인한 현재 최신 버전이다.
> 구현 착수 전 **반드시 `docs_manifest.md §1`을 먼저 조회**하여 버전이 여전히 최신인지 검증한다.
> 본 명세서에 기재된 버전과 docs_manifest §1 버전이 다르면 **즉시 PM에게 알리고 명세서 갱신을 요청**한다.

| 문서 | 버전 (docs_manifest §1 기준) | 참조 목적 | 확인 |
|------|------|-----------|------|
| `api_spec_vN.md §참조 엔드포인트` | **v5** | 엔드포인트·request·response 필드명 | ☐ |
| `db_schema_vN.md §참조 테이블, §배치 관리 테이블` | **v5** | 참조 테이블 구조·컬럼·UNIQUE 키 | ☐ |
| `exception_spec_vN.md §API-COM, §API-VAL, §PARSE-DATE, §PARSE-ENUM` | **v6** | 이 기능에 해당하는 에러 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md` | **v3** | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2 디렉토리 구조, §6 타입 정의, §8.4 예외 클래스` | **v4** | 프레임 디렉토리 구조·타입 파일 위치·`ParseError` 클래스 정의 확인 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

`commodities`, `segments`, `external_events`, `baselines`, `cointegration_results`, `data_freshness` 테이블을 조회하여 참조 엔드포인트 5개(`/commodities`, `/commodities/{id}`, `/segments`, `/events`, `/freshness`)를 구현하고 200 OK 응답을 반환한다.

### 1.2 데이터 흐름

```
[GET /commodities]
  commodities 테이블 전체 조회
  → (Phase 7 완료 전) has_anomaly_this_month=null, latest_anomaly_grade=null 더미 반환
  → CommodityListResponse Pydantic 직렬화 (DATE → YYYY-MM)
  → JSON 응답

[GET /commodities/{commodity_id}]
  commodities 테이블 단건 조회 (commodity_id 일치)
  JOIN baselines (subperiod_id IS NULL — 전체 기간 기준선만, D-15)
  JOIN cointegration_results (cointegrated 필드)
  JOIN segments (upstream_label, downstream_label)
  → segment_meta 구간별(A/B/C/D/D′) 조합
  → CommodityDetailResponse Pydantic 직렬화
  → JSON 응답

[GET /segments]
  segments 테이블 전체 조회 (정적)
  → ETag + Cache-Control: max-age=86400 헤더 포함
  → SegmentListResponse Pydantic 직렬화
  → JSON 응답

[GET /events]
  external_events 테이블 전체 조회 (정적)
  → ETag + Cache-Control: max-age=86400 헤더 포함
  → EventListResponse Pydantic 직렬화
  → JSON 응답

[GET /freshness]
  data_freshness 테이블 최신 1개 행 조회 (data_up_to, next_run_date, last_updated 직접 반환)
  → FreshnessResponse Pydantic 직렬화 (last_updated: ISO 8601)
  → JSON 응답
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2 디렉토리 구조` 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/api/v1/endpoints/commodities.py` | `/commodities`, `/commodities/{commodity_id}` 라우트 함수 구현 |
| 수정 | `app/api/v1/endpoints/meta.py` | `/segments`, `/events`, `/freshness` 라우트 함수 구현 |
| 수정 | `app/schemas/commodity.py` | `CommodityListResponse`, `CommodityDetailResponse`, `SegmentListResponse` Pydantic 스키마 완성 |
| 수정 | `app/schemas/meta.py` | `EventListResponse`, `FreshnessResponse` Pydantic 스키마 완성 |
| 신규 | `app/services/reference.py` | 참조 엔드포인트 DB 쿼리 비즈니스 로직 모듈 |
| 신규 | `tests/fixtures/reference_dummy.json` | 더미 응답 픽스처 (5개 엔드포인트) |
| 신규 | `tests/test_api_reference.py` | 참조 엔드포인트 통합 테스트 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | `/commodities` — 10개 품목 목록 + `has_anomaly_this_month`(더미 null) + `latest_anomaly_grade`(더미 null) 반환 |
| **구현** | `/commodities/{commodity_id}` — 단일 품목 상세 + `segment_meta` 전체 구간 + `warmup_end` (`baselines.warmup_end` 직접 반환, D-06) |
| **구현** | `/segments` — 분석 구간 정의 5개 전체 반환 + ETag + Cache-Control |
| **구현** | `/events` — 외부 충격 이벤트 5개 전체 반환 + ETag + Cache-Control |
| **구현** | `/freshness` — `data_freshness` 테이블 최신 1개 행에서 `data_up_to`, `next_run_date`, `last_updated` 직접 반환 |
| **구현** | `COMMODITY_NOT_FOUND` (404), `PIPELINE_DATA_MISSING` (500) 에러 응답 |
| **구현** | `baselines`, `cointegration_results` ORM 모델 임시 정의 + Alembic revision(`0003_add_baselines.py`, `0004_add_cointegration_results.py`) 수동 작성 — `frame_spec_backend_vN §8.6` 분할 원칙과 충돌하므로 **PM 확인 후 진행** |
| **비구현** | `has_anomaly_this_month` / `latest_anomaly_grade` 실제 `anomaly_results` 집계 — Phase 7 완료 후 `feat/be-api-anomaly`에서 연동 |
| **비구현** | Redis TTL 캐싱 — `feat/be-redis`에서 구현 |
| **선행 조건** | `frame/backend` dev 머지 완료 (더미 DB 시드 포함: `commodities` 10행, `segments` 5행, `external_events` 5행) |

---

## 2. 입력 데이터

| 출처 | 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|---------|-----------|------|------|
| DB 테이블 | `commodities` | `commodity_id`, `name_kr`, `name_en`, `cluster`, `has_wholesale`, `route_type`, `analysis_start`, `analysis_end` | 각 컬럼 타입 per **db_schema_vN** | `analysis_start`/`analysis_end`는 `DATE` → `YYYY-MM` 변환 |
| DB 테이블 | `segments` | `segment_id`, `label_kr`, `upstream_label`, `downstream_label`, `applies_to`, `pattern1`, `pattern2`, `pattern3`, `ml_applied` | per **db_schema_vN** | 정적 데이터. `/commodities/{id}`의 `segment_meta` 구성 시 JOIN 사용 |
| DB 테이블 | `external_events` | `event_key`, `label_kr`, `start_date`, `end_date`, `color_hex` | per **db_schema_vN** | 정적 데이터. `start_date`/`end_date`는 `DATE` → `YYYY-MM` 변환 |
| DB 테이블 | `baselines` | `commodity_id`, `segment_id`, `normal_transmission_lag`, `transmission_elasticity`, `warmup_end`, `subperiod_id`, `model_type` | per **db_schema_vN** | `subperiod_id IS NULL` 조건으로 전체 기간 기준선만 조회 (D-15) |
| DB 테이블 | `cointegration_results` | `commodity_id`, `segment_id`, `cointegrated` | per **db_schema_vN** | `/commodities/{id}` `segment_meta.cointegrated` 출처. `baselines`와 JOIN |
| DB 테이블 | `data_freshness` | `data_up_to`, `next_run_date`, `last_updated` | `DATE`, `DATE`, `TIMESTAMPTZ` | 항상 최신 1개 행. `last_updated`는 ISO 8601 직렬화 |

> **`baselines` 테이블 ORM 모델**: Frame 단계 미포함 테이블. `frame_spec_backend_vN §8.6`에서 `feat/pipeline-phase4-5` 소관으로 배정되어 있으나, 이 브랜치에서 `/commodities/{id}` 구현에 필요하므로 `app/db/models/` 하위에 임시 정의하고 Alembic revision(`0003_add_baselines.py`)을 수동 작성한다. **⚠️ PM 확인 필요**: `feat/pipeline-phase4-5` 착수 시 중복 정의 충돌 방지를 위해 브랜치 조율 필요.
>
> **`cointegration_results` 테이블 ORM 모델**: Frame 단계 미포함 테이블. `frame_spec_backend_vN §8.6`에서 `feat/pipeline-phase2-3` 소관으로 배정되어 있으나, 이 브랜치에서 `segment_meta.cointegrated` 조회에 필요하므로 동일하게 임시 정의가 필요하다. **⚠️ PM 확인 필요**: `feat/pipeline-phase2-3`과의 착수 순서 및 ORM 정의 중복 충돌 방지 조율 필요.

### 2.1 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| DB → API 응답 | `DATE` (`analysis_start`, `analysis_end`, `warmup_end`) | `YYYY-MM` 문자열 | Pydantic serializer `strftime("%Y-%m")` (D-11) |
| DB → API 응답 | `DATE` (`start_date`, `end_date` in `external_events`) | `YYYY-MM` 문자열 | 동일 |
| DB → API 응답 | `DATE` (`data_up_to` in `data_freshness`) | `YYYY-MM` 문자열 | 동일. 월 단위 기준 시점이므로 `YYYY-MM` 적용 |
| DB → API 응답 | `DATE` (`next_run_date` in `data_freshness`) | `YYYY-MM-DD` 문자열 | `api_spec_vN §GET /freshness` 응답 예시 기준 일 단위 날짜 표기. `YYYY-MM` 변환 적용 **안 함** |
| DB → API 응답 | `TIMESTAMPTZ` (`last_updated` in `data_freshness`) | ISO 8601 문자열 | `last_updated` 필드로 그대로 직렬화 (`YYYY-MM-DDTHH:MM:SSZ`) |

---

## 3. 출력 데이터

### 3.1 API 응답

| 엔드포인트 | 주 참조 테이블 | 응답 필드 | 비고 |
|------------|---------------|-----------|------|
| `GET /api/v1/commodities` | `commodities` | `commodities[]` (아래 필드 목록) | `has_anomaly_this_month`·`latest_anomaly_grade` Phase 7 전 null |
| `GET /api/v1/commodities/{commodity_id}` | `commodities`, `baselines`, `cointegration_results`, `segments` | `/commodities` 단일 품목 필드 + `segment_meta` | `baselines.subperiod_id IS NULL` 조건 (D-15). `cointegrated`는 `cointegration_results` 조회. `upstream_label`/`downstream_label`은 `segments` JOIN |
| `GET /api/v1/segments` | `segments` | `segments[]` | ETag + `Cache-Control: max-age=86400` |
| `GET /api/v1/events` | `external_events` | `events[]` | ETag + `Cache-Control: max-age=86400` |
| `GET /api/v1/freshness` | `data_freshness` | `data_up_to`, `next_run_date`, `last_updated` | `last_updated`: ISO 8601 |

**`GET /commodities` 응답 필드 상세** (`api_spec_vN.md §GET /commodities` 기준)

| 필드 | 타입 | 출처 컬럼 | 비고 |
|------|------|-----------|------|
| `commodity_id` | string | `commodities.commodity_id` | |
| `name_kr` | string | `commodities.name_kr` | |
| `name_en` | string | `commodities.name_en` | |
| `cluster` | string | `commodities.cluster` | Literal: `"grain"` \| `"oil_sugar"` \| `"tropical"` \| `"livestock"` \| `"independent"` |
| `has_wholesale` | boolean | `commodities.has_wholesale` | |
| `route_type` | string | `commodities.route_type` | Literal: `"3seg"` \| `"4seg"` |
| `segments` | string[] | `commodities.route_type` 기반 파생 | `"3seg"` → `["A","B","D_prime"]`, `"4seg"` → `["A","B","C","D"]` |
| `analysis_start` | `YYYY-MM` | `commodities.analysis_start` | DATE → YYYY-MM |
| `analysis_end` | `YYYY-MM` | `commodities.analysis_end` | DATE → YYYY-MM |
| `has_anomaly_this_month` | boolean | (더미) | Phase 7 전 `false` 반환. `api_spec_vN §GET /commodities`는 `boolean` non-nullable 정의 |
| `latest_anomaly_grade` | `"high"` \| `"medium"` \| `"reference"` \| null | (더미) | Phase 7 전 null. `api_spec_vN §GET /commodities` 기준 Literal 타입 |

**`GET /commodities/{id}` 추가 필드 상세** (`api_spec_vN.md §GET /commodities/{commodity_id}` + D-06, D-15)

| 필드 | 타입 | 출처 컬럼 | 비고 |
|------|------|-----------|------|
| `segment_meta.{seg}.model_type` | string | `baselines.model_type` | Literal: `"VECM"` \| `"VAR"` |
| `segment_meta.{seg}.cointegrated` | boolean | `cointegration_results.cointegrated` | |
| `segment_meta.{seg}.normal_transmission_lag` | integer | `baselines.normal_transmission_lag` | 전체 기간 기준선 (`subperiod_id IS NULL`) |
| `segment_meta.{seg}.transmission_elasticity` | number | `baselines.transmission_elasticity` | 전체 기간 기준선 |
| `segment_meta.{seg}.upstream_label` | string | `segments.upstream_label` | `segments` 테이블 JOIN 필요 |
| `segment_meta.{seg}.downstream_label` | string | `segments.downstream_label` | `segments` 테이블 JOIN 필요 |
| `segment_meta.{seg}.warmup_end` | `YYYY-MM` | `baselines.warmup_end` | 직접 반환, 별도 집계 없음 (D-06) |

---

## 4. 파라미터 제약 조건

해당 없음. 이 브랜치의 참조 엔드포인트는 모두 쿼리 파라미터가 없다. `settings.py` 참조 파라미터 불필요.

> `/segments`, `/events`의 ETag 값은 서버 기동 시 응답 본문 해시로 1회 계산하여 메모리에 보관한다. 하드코딩 금지.

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스. 이 기능에 해당하는 코드의 발생 조건·처리 방침 확인 시 참조한다.
> - **`exception_design_vN.md`**: 에러 체이닝 구현 설계. 실제 코드 작성 시 이 문서의 구현 패턴을 따른다.

### 5.1 적용 예외 코드

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `API-COM-001` | `/commodities/{commodity_id}` — 존재하지 않는 `commodity_id` 요청 | CLIENT_404 (`COMMODITY_NOT_FOUND`) |
| `API-COM-002` | 참조/시각화 엔드포인트 전반 — 품목은 있으나 `analysis_start`가 NULL (Phase 0 미완) | CLIENT_500 (`PIPELINE_DATA_MISSING`) |
| `API-VAL-001` | Pydantic 검증 실패 (비정상 요청) | CLIENT_400 |
| `API-INT-001` | 핸들러 미매핑 내부 예외 | CLIENT_500 (`INTERNAL_ERROR`) |
| `PARSE-DATE-001` | `DATE` → `YYYY-MM` 직렬화 실패 (`analysis_start`, `warmup_end` 등) | CLIENT_500 |
| `PARSE-ENUM-001` | `cluster`, `route_type`, `model_type` 등 Pydantic Literal 외 DB 값 | CLIENT_500 |
| `CFG-CORE-001` | 필수 환경변수(`DATABASE_URL`, `REDIS_URL` 등) 누락 — 부팅 시 감지 | FATAL (부팅 중단) |
| `DB-CONN-001` | DB 연결 실패 | FATAL (lifespan에서 처리) |
| `DB-CACHE-001` | Redis 연결 실패 | WARN — ETag 캐싱 skip, DB 직접 조회로 계속 |

### 5.2 신규 예외 코드 제안

해당 없음. 기존 코드로 모든 케이스 처리 가능.

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간), `banana` (4구간) |
| 테스트 기간 | Frame 시드 데이터 기준 (`db_schema_vN §초기 데이터` 10행) |
| 특수 케이스 | 존재하지 않는 `commodity_id` 요청 → `COMMODITY_NOT_FOUND` 404 / `baselines` 미적재 상태에서 `/commodities/{id}` 요청 → `segment_meta` 빈 객체 또는 `PIPELINE_DATA_MISSING` 500 |
| 더미 픽스처 위치 | `tests/fixtures/reference_dummy.json` |
| 더미 → 실제 전환 트리거 | `baselines` 테이블 적재 완료 후 자동 전환 (쿼리 구조 동일, 더미 분기 없음). `has_anomaly_this_month`·`latest_anomaly_grade` 실제 연동은 `feat/be-api-anomaly`에서 별도 처리 |

---

## 7. 완료 기준

| 항목 | 기준 |
|------|------|
| 기능 완성 | 5개 엔드포인트 전부 200 OK 확인 (더미 DB 시드 기반, wheat·banana 포함) |
| 응답 필드명·타입 | `api_spec_vN.md §참조 엔드포인트` 필드명·타입 100% 일치, 누락 0개 |
| snake_case 유지 | alias 변환 없음. Pydantic `alias_generator` 미사용 확인 |
| 타입 변환 | `DATE` → `YYYY-MM` 직렬화 확인 (`analysis_start`, `warmup_end`, `start_date` 등 전 필드). `next_run_date`는 `YYYY-MM-DD` 유지 확인 |
| 캐싱 헤더 | `/segments`, `/events` 응답에 `ETag` + `Cache-Control: max-age=86400` 포함 확인 |
| 에러 응답 | 존재하지 않는 `commodity_id` 요청 시 `COMMODITY_NOT_FOUND` 404 + 에러 envelope (`api_spec_vN.md §에러 형식`) 확인 |
| 예외처리 | §5.1 예외 코드 발생 시 정의된 방침대로 처리 확인 |
| Alembic | `0003_add_baselines.py`, `0004_add_cointegration_results.py` revision 적용 완료 (`alembic upgrade head` 오류 없음) |
| 테스트 | `tests/test_api_reference.py` 전 케이스 통과 |
| 결과 명세 | `docs/results/API-REF.md` 작성 완료 (응답 샘플 포함) |
| **재검증** | §10 문서 버전 재검증 체크리스트 전 항목 ☑ 확인 후 PR 제출 |
| 후속 선행 조건 | `feat/be-batch` 착수 가능 상태 |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| `has_anomaly_this_month`·`latest_anomaly_grade` 실제 `anomaly_results` 집계 구현 | Phase 7 미완료. `feat/be-api-anomaly`에서 담당 |
| Redis TTL 캐싱 로직 구현 | `feat/be-redis` 담당 |
| Pydantic `alias_generator`로 camelCase 변환 | `frame_spec_backend_vN §6.1` 정책 위반 |
| `baselines` 조회 시 `subperiod_id IS NULL` 조건 누락 | 하위 기간 기준선 혼입 방지 (D-15) |
| `warmup_end` 별도 집계 쿼리 작성 | `baselines.warmup_end` 직접 반환 원칙 위반 (D-06) |
| `segments` 배열을 코드 하드코딩으로 반환 | `commodities.route_type` 기반 파생 로직으로 처리해야 함 |
| ORM 모델을 endpoint 함수에서 직접 반환 | `frame_spec_backend_vN §5` 정책 위반 — service 함수에서 Pydantic 변환 필수 |
| Alembic `autogenerate` 사용 | `frame_spec_backend_vN §8.9` 위반 — 수동 작성 필수 |
| `next_run_date`를 `YYYY-MM`으로 변환 | `api_spec_vN §GET /freshness` 기준 `YYYY-MM-DD` 유지 필수 |
| `latest_anomaly_grade`를 임의 문자열 타입으로 정의 | Literal `"high"` \| `"medium"` \| `"reference"` \| null 강제 (§3.1 기준) |

---

## 9. Pull Request 템플릿

> `feat/be-api-reference` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-api-reference
- **기능 번호**: API-REF
- **Feature 명세**: `docs/feature_spec_API-REF_v4.md`
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] 기능 완성: 5개 엔드포인트 200 OK (wheat·banana 포함, 더미 시드 기반)
- [ ] 응답 필드명·타입 api_spec_vN 일치 (누락 0개)
- [ ] snake_case 유지 (alias 변환 없음)
- [ ] DATE → YYYY-MM 직렬화 전 필드 확인 (next_run_date는 YYYY-MM-DD 유지 확인)
- [ ] ETag + Cache-Control 헤더 (/segments, /events)
- [ ] COMMODITY_NOT_FOUND 404 에러 envelope 확인
- [ ] §5.1 예외처리 구현 확인
- [ ] 0003_add_baselines.py, 0004_add_cointegration_results.py Alembic revision 적용 완료
- [ ] tests/test_api_reference.py 전 케이스 통과
- [ ] docs/results/API-REF.md 작성 완료
- [ ] §10 문서 버전 재검증 체크리스트 전 항목 ☑ 완료

## 필드명 3방향 일치 확인
- [ ] `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/` 필드명 일치
- [ ] Literal 타입 일치: `cluster`, `route_type`, `model_type`, `latest_anomaly_grade`
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: `API-COM-001`, `API-COM-002`, `API-VAL-001`, `API-INT-001`, `CFG-CORE-001`, `DB-CONN-001`, `PARSE-DATE-001`, `PARSE-ENUM-001`, `DB-CACHE-001`
- 신규 제안 코드: 없음

## 비구현 항목 (후속 브랜치 담당)
- has_anomaly_this_month / latest_anomaly_grade 실제 집계 → feat/be-api-anomaly
- Redis TTL 캐싱 → feat/be-redis

## 로컬 실행 증빙
{로그·스크린샷·테스트 출력 붙여넣기}

## 리뷰어 확인 요청 사항
- baselines, cointegration_results ORM 임시 정의 방식 및 feat/pipeline-phase2-3·4-5와 브랜치 조율 방안 확인 (frame_spec_backend_vN §8.6 분할 원칙 충돌)
- segment_meta upstream_label/downstream_label 조회를 위한 segments JOIN 방식 최종 확인
- segment_meta warmup_end 직접 반환 방식 최종 확인 (D-06)
- ETag 계산 방식 (응답 본문 해시) 승인

## 기타
- Alembic revision 0003_add_baselines.py, 0004_add_cointegration_results.py 신규 추가
- 배포 영향: 해당 없음 (신규 엔드포인트, 기존 로직 변경 없음)
```

---

## 10. 문서 버전 재검증 체크리스트

> **신설 목적**: v2 → v3에서 발견된 중대 결함(참조 문서 전체가 구버전으로 고정) 재발 방지.
> **수행 시점**: PR 제출 전 반드시 완료. 체크 결과를 PR 본문에 기록한다.
> **수행 주체**: 구현 담당자(샤킬라) + PM 검토.

### 10.1 docs_manifest §1 버전 최신성 검증

> 이 섹션에 기재된 "현재 버전"은 명세서 작성 시점 기준이다. PR 시점에 `docs_manifest.md §1`을 다시 조회하여 최신 버전과 일치하는지 재확인한다.

| 문서 ID | 이 명세서 작성 시점 버전 | PR 시점 docs_manifest §1 확인 버전 | 일치 여부 |
|---------|---------|---------|---------|
| `api_spec` | v5 | {PR 시 기입} | ☐ |
| `db_schema` | v5 | {PR 시 기입} | ☐ |
| `exception_spec` | v6 | {PR 시 기입} | ☐ |
| `exception_design` | v3 | {PR 시 기입} | ☐ |
| `frame_spec_backend` | v4 | {PR 시 기입} | ☐ |

> **불일치 발생 시**: 즉시 구현 중단 → PM에게 명세서 갱신 요청 → 갱신된 명세서 기준으로 재구현.

### 10.2 3-way 타입 일치 검증 (db_schema ↔ api_spec ↔ Pydantic 스키마)

| 점검 항목 | 확인 |
|-----------|------|
| `db_schema_vN §commodities` 컬럼명 ↔ `api_spec_vN §GET /commodities` 응답 필드명 1:1 일치 | ☐ |
| `db_schema_vN §segments` 컬럼명 ↔ `api_spec_vN §GET /segments` 응답 필드명 1:1 일치 | ☐ |
| `db_schema_vN §external_events` 컬럼명 ↔ `api_spec_vN §GET /events` 응답 필드명 1:1 일치 | ☐ |
| `db_schema_vN §baselines` 컬럼명 ↔ `api_spec_vN §GET /commodities/{id}` `segment_meta` 필드명 1:1 일치 | ☐ |
| `db_schema_vN §data_freshness` 컬럼명 ↔ `api_spec_vN §GET /freshness` 응답 필드명 1:1 일치 | ☐ |
| `cluster` Literal: `db_schema_vN` ↔ `api_spec_vN` ↔ `app/schemas/commodity.py` 3방향 일치 | ☐ |
| `route_type` Literal: `db_schema_vN` ↔ `api_spec_vN` ↔ `app/schemas/commodity.py` 3방향 일치 | ☐ |
| `model_type` Literal: `db_schema_vN §baselines` ↔ `api_spec_vN §segment_meta` ↔ `app/schemas/commodity.py` 3방향 일치 | ☐ |
| `latest_anomaly_grade` Literal (`"high"` \| `"medium"` \| `"reference"` \| null): `api_spec_vN` ↔ `app/schemas/commodity.py` 일치 | ☐ |

### 10.3 예외처리 코드 유효성 검증

| 점검 항목 | 확인 |
|-----------|------|
| §5.1의 모든 예외 코드가 `exception_spec_vN §2` 인덱스에 존재하는지 확인 | ☐ |
| 각 코드의 처리 방침이 `exception_spec_vN §1.5` 정의와 일치하는지 확인 (`CLIENT_404`, `CLIENT_500`, `WARN`, `FATAL`) | ☐ |
| `exception_design_vN`의 에러 체이닝 패턴을 코드에 적용했는지 확인 | ☐ |

### 10.4 직렬화·변환 규칙 검증

| 점검 항목 | 확인 |
|-----------|------|
| `DATE` → `YYYY-MM` 대상 필드 목록(§2.1)이 `api_spec_vN §공통 사항 (D-11)` 방침과 일치하는지 확인 | ☐ |
| `next_run_date` → `YYYY-MM-DD` (변환 미적용) 규칙이 `api_spec_vN §GET /freshness` 응답 예시와 일치하는지 확인 | ☐ |
| `last_updated` → ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`) 직렬화 규칙 확인 | ☐ |

### 10.5 frame_spec_backend_vN 정책 준수 검증

| 점검 항목 | 확인 |
|-----------|------|
| 파일 경로가 `frame_spec_backend_vN §2 디렉토리 구조`와 일치하는지 확인 | ☐ |
| ORM 모델을 endpoint에서 직접 반환하지 않았는지 확인 (`frame_spec_backend_vN §5`) | ☐ |
| Pydantic `alias_generator` 미사용 확인 (`frame_spec_backend_vN §6.1`) | ☐ |
| Alembic `autogenerate` 미사용, 수동 revision 작성 확인 (`frame_spec_backend_vN §8.9`) | ☐ |
