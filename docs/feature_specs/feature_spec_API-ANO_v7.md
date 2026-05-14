# Feature 명세서 — 이상 탐지 요약 엔드포인트

**문서 유형**: Feature 명세서
**기능 번호**: `API-ANO`
**브랜치명**: `feat/be-api-anomaly`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-05-04
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-05-04): 최초 작성
- v2 (2026-05-04): 검토 수정. §2 `commodities` 테이블 조인 출처 누락 추가. §5.1 `API-ANO-001` 비해당 명확화, `API-VAL-001` 전역 핸들러 자동 처리 명시. §1.3·§6 fixture 경로 미확정 표기. §9 PM 확인 항목 2개 추가.
- v3 (2026-05-05): 누락 보완. §2 `anomaly_results.pattern_types` 컬럼 추가 및 `data_freshness` 조회 방법(`ORDER BY id DESC LIMIT 1`) 명시. §3 응답 필드 전체 명세 테이블 신규 추가 (타입·DB 출처·변환 규칙 포함). §9 `pattern_types` 응답 포함 여부 PM 확인 항목 추가.
- v4 (2026-05-05): 오류·누락 수정. §1.4 실제 연동 단계 선행 조건(`feat/phase7-stat`) 추가 및 스프린트(S2 후반~S3) 행 추가. §6 테스트 품목 구간 수 오기 수정 (`wheat` 4→3구간, `banana` 3→4구간, `db_schema_vN.md §commodities` 기준).
- v5 (2026-05-05): 누락 보완. §6 더미 단계 응답 출처 명시(`frame_spec_backend_vN.md §8.1` 기준 빈 배열 vs fixture 샘플 중 PM 확인 필요). §7 완료 기준을 더미 단계·실제 연동 단계 2단계로 분리하여 실제 연동 완료 기준 4개 항목 추가. §9 PM 승인란에 더미 응답 방식 확정 항목 추가. §10 PR 템플릿 구현 완료 항목을 2단계로 분리.
- v6 (2026-05-05): PM 검토 반영. §3 `pattern_types` 행 삭제 (`api_spec_vN §GET /anomalies/summary` 응답 필드 미명시, `/stream anomaly_nodes`와 의도적 구분 확정). §1.3 fixture 행 삭제 (더미 응답 고정값 방식 확정으로 불필요). §6 더미 단계 응답 방식 빈 배열 고정값으로 확정 기재 (fixture 파일 불필요 명시). §7 더미 단계 "집계 정확성" 완료 기준을 고정값 기준으로 수정. §9 PM 확인 항목 중 결정 완료 3건 확정 처리. §10 PR 템플릿 명세서 버전 오기 수정 (`v1` → `v6`).
- v7 (2026-05-11): 참조 문서 버전 갱신. §0 `exception_spec_vN.md` v5 → v6, `frame_spec_backend_vN.md` v3 → v4 수정.

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `db_schema_vN.md §anomaly_results` | v5 | 적재 테이블 구조·UNIQUE 키·필터 조건 | ☐ |
| `db_schema_vN.md §data_freshness` | v5 | 기준 월 조회 테이블 | ☐ |
| `api_spec_vN.md §요약 엔드포인트` | v5 | 엔드포인트·request·response 필드명 | ☐ |
| `exception_spec_vN.md §2.2, §8` | v6 | 이 기능에 해당하는 에러 코드·처리 방침 | ☐ |
| `exception_design_vN.md §2` | v3 | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2, §8` | v4 | 프레임 디렉토리 구조·예외 핸들러·라우터 정책 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

`anomaly_results` 테이블을 집계하여 기준 월의 이상 탐지 목록·건수·전월 대비 증감을 JSON으로 반환하는 요약 엔드포인트를 구현한다.

### 1.2 데이터 흐름

```
anomaly_results 테이블 (confidence_grade, period, is_new 등)
  + data_freshness 테이블 (최신 기준 월 조회)
  → SQLAlchemy 비동기 쿼리
    (month 파라미터 필터 + grade 파라미터 필터)
  → 기준 월 건수·전월 건수·증감 집계
  → Pydantic 직렬화 (DATE → YYYY-MM 변환)
  → GET /api/v1/anomalies/summary JSON 응답
```

### 1.3 프레임 내 위치

`frame/backend` 기준 디렉토리 구조(`frame_spec_backend_vN.md §2`)에서 아래 파일에 코드를 추가·수정한다.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/api/v1/endpoints/anomalies.py` | `GET /anomalies/summary` 라우트 핸들러 추가 |
| 수정 | `app/schemas/anomaly.py` | `AnomalySummaryResponse`, `AnomalySummaryItem` Pydantic 스키마 추가 |
| 신규 | `app/services/anomaly_summary.py` | 요약 집계 비즈니스 로직 분리 |

> **fixture 파일 불필요**: 더미 단계 응답이 고정값(빈 배열) 방식으로 확정되어 별도 fixture 파일을 생성하지 않는다. (`frame_spec_backend_vN.md §8.1` 정책 준수, §6 참조)

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **스프린트** | S2 후반~S3 (`feature_dev_list_vN.md §feat/be-api-anomaly` 기준) |
| **구현** | `GET /api/v1/anomalies/summary` 엔드포인트 1개 구현 (쿼리 파라미터: `grade`, `month`) |
| **구현** | 더미 DB 기반 200 OK 확인 (Phase 7-stat 완료 전 단계) |
| **구현** | `grade` 파라미터 콤마 구분 복수 지정 파싱 |
| **구현** | `month` 미지정 시 `data_freshness` 테이블에서 최신 기준 월 자동 조회 |
| **비구현** | `feat/phase7-stat` 완료 전 실제 이상 데이터 연동 (더미 `anomaly_results` 사용) |
| **비구현** | Redis 캐싱 (해당 없음 — 이 엔드포인트는 `feat/be-redis` 캐싱 대상 외) |
| **비구현** | 페이지네이션 (`api_spec_vN §요약 엔드포인트` 명세에 없음) |
| **선행 조건 (더미 단계)** | `frame/backend` dev 머지 완료 (디렉토리 구조·ORM 모델 9개·예외 핸들러 등록 상태) |
| **선행 조건 (실제 연동 단계)** | `feat/phase7-stat` dev 머지 완료 — `anomaly_results` 테이블 실제 데이터 적재 확인 후 서비스 로직 전환 |

---

## 2. 입력 데이터

| 출처 | 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|----------|-----------|------|------|
| DB 테이블 | `anomaly_results` | `id`, `commodity_id`, `segment_id`, `period`, `primary_pattern`, `confidence_grade`, `is_new`, `transmission_rate` | 각 컬럼 타입은 `db_schema_vN.md §anomaly_results` 기준 | `confidence_grade IS NOT NULL` 행만 존재 (D-02). `pattern_types`는 DB에서 조회하나 응답에 포함하지 않음 (§3 참조) |
| DB 테이블 | `commodities` | `name_kr` | `VARCHAR(50)` | `anomaly_results.commodity_id` 기준 JOIN — 응답 `commodity_name_kr` 필드 출처 |
| DB 테이블 | `data_freshness` | `data_up_to` | `DATE` | `month` 파라미터 미지정 시 기준 월 조회용. **조회 방법**: `db_schema_vN.md §data_freshness`에 "항상 최신 1개 행만 유지" 정책 명시 → `SELECT data_up_to FROM data_freshness ORDER BY id DESC LIMIT 1` |
| 쿼리 파라미터 | — | `grade` | `string` | 기본값 `"high,medium"`, 콤마 구분 복수 지정 |
| 쿼리 파라미터 | — | `month` | `YYYY-MM` | 기본값: `data_freshness.data_up_to` |

**쿼리 파라미터 검증 규칙**

| 파라미터 | 허용 값 | 오류 시 |
|----------|---------|---------|
| `grade` | `high`, `medium`, `reference` 중 콤마 구분 복수 | `API-VAL-001` → 400 |
| `month` | `YYYY-MM` 형식 (zero-pad 필수) | `API-VAL-001` → 400 |

### 2.1 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| DB → API 응답 | `DATE (YYYY-MM-01)` | `YYYY-MM` 문자열 | Pydantic serializer `strftime("%Y-%m")` |
| DB → API 응답 | `anomaly_results.id` (SERIAL) | `anomaly_id` (integer) | 필드명 매핑 (DB `id` → 응답 `anomaly_id`) |

---

## 3. 출력 데이터

### 3.1 API 응답

`api_spec_vN.md §요약 엔드포인트` 기준.

| 엔드포인트 | 주 참조 테이블 | 응답 필드 | 비고 |
|------------|---------------|-----------|------|
| `GET /api/v1/anomalies/summary` | `anomaly_results` | `reference_month`, `total_count`, `prev_month_count`, `count_diff`, `anomalies[]` | 이상 없는 월: `anomalies: []` (null 아님) |

**응답 구조 (`api_spec_vN.md §GET /anomalies/summary` 기준)**

```json
{
  "reference_month": "2026-03",
  "total_count": 5,
  "prev_month_count": 3,
  "count_diff": 2,
  "anomalies": [
    {
      "anomaly_id": 142,
      "commodity_id": "wheat",
      "commodity_name_kr": "밀",
      "segment_id": "A",
      "period": "2026-03",
      "primary_pattern": "pattern2",
      "confidence_grade": "high",
      "is_new": true,
      "transmission_rate": 1.43
    }
  ]
}
```

**집계 규칙**

| 필드 | 집계 방법 |
|------|-----------|
| `total_count` | 기준 월(`period = YYYY-MM-01`) + `grade` 필터 적용 후 행 수. UNIQUE `(commodity_id, segment_id, period)` 이므로 동월 복수 패턴도 1건으로 계산됨 |
| `prev_month_count` | 기준 월 -1개월 동일 `grade` 필터 적용 행 수 |
| `count_diff` | `total_count - prev_month_count` (양수 = 증가) |
| `anomalies` | 기준 월 + `grade` 필터 적용 행 전체 반환. `commodity_name_kr`은 `commodities` 테이블 조인 |

**응답 필드 전체 명세 (Pydantic `AnomalySummaryItem` 스키마 작성 기준)**

| 필드명 | 타입 | DB 출처 | 변환 규칙 | 비고 |
|--------|------|---------|-----------|------|
| `reference_month` | `str` | `data_freshness.data_up_to` 또는 `month` 파라미터 | `DATE → YYYY-MM` (`strftime`) | 최상위 필드 |
| `total_count` | `int` | `anomaly_results` 집계 | — | 최상위 필드 |
| `prev_month_count` | `int` | `anomaly_results` 집계 (기준 월 -1) | — | 최상위 필드 |
| `count_diff` | `int` | `total_count - prev_month_count` | — | 음수 가능 |
| `anomalies[].anomaly_id` | `int` | `anomaly_results.id` | 필드명 매핑 (`id` → `anomaly_id`) | 패널 진입 키 |
| `anomalies[].commodity_id` | `str` | `anomaly_results.commodity_id` | — | `VARCHAR(20)` |
| `anomalies[].commodity_name_kr` | `str` | `commodities.name_kr` | — | JOIN 필드 |
| `anomalies[].segment_id` | `str` | `anomaly_results.segment_id` | — | `VARCHAR(10)` |
| `anomalies[].period` | `str` | `anomaly_results.period` | `DATE → YYYY-MM` (`strftime`) | |
| `anomalies[].primary_pattern` | `Literal['pattern1','pattern2','pattern3']` | `anomaly_results.primary_pattern` | — | `frame_spec_backend_vN.md §6.2` Literal 필수 |
| `anomalies[].confidence_grade` | `Literal['high','medium','reference']` | `anomaly_results.confidence_grade` | — | `frame_spec_backend_vN.md §6.2` Literal 필수 |
| `anomalies[].is_new` | `bool` | `anomaly_results.is_new` | — | NEW 배지 표시용 |
| `anomalies[].transmission_rate` | `float \| None` | `anomaly_results.transmission_rate` | `NUMERIC(12,6) → float` | 패턴 1 단독 탐지 시 `None` 가능 |

> **`pattern_types` 미포함 근거**: `api_spec_vN §GET /anomalies/summary` 응답 필드 테이블에 명시되지 않은 필드다. 동일 파일의 `/stream anomaly_nodes`에는 `pattern_types`가 명시되어 있어 두 엔드포인트를 의도적으로 구분한 설계다. 요약 배너는 배지·건수·등급 표시용 경량 응답이 목적이므로 `primary_pattern`만으로 충분하며, `pattern_types` 상세는 패널 엔드포인트(`/anomalies/{id}/detail`)에서 제공한다.

---

## 4. 파라미터 제약 조건

해당 없음. 이 기능에서 `settings.py` 참조 고정 파라미터는 사용하지 않는다.

---

## 5. 예외처리

> - **`exception_spec_vN.md §2.2, §8`**: 에러 코드 인덱스 및 기능별 매핑 참조.
> - **`exception_design_vN.md §2`**: 에러 체이닝 구현 방식 (`raise X from e` 필수).

### 5.1 적용 예외 코드

`exception_spec_vN.md §8` 기준 `feat/be-api-anomaly` 구현 필수 코드: `API-ANO-001`, `API-INT-001`

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `API-ANO-001` | `/anomalies/summary`는 `anomaly_id` 경로 파라미터가 없으므로 **이 엔드포인트에서는 발생하지 않음**. `exception_spec_vN.md §8` 매핑상 이 브랜치에 포함되어 있으나 실제 구현 대상 아님 | — |
| `API-INT-001` | 집계 쿼리 실패, 예상치 못한 내부 예외 | CLIENT_500 |
| `API-VAL-001` | `grade` 허용 값 외 입력, `month` 형식 오류 (`YYYY-M`, `YYYY-MM-DD` 등) — **`frame_spec_backend_vN.md §8.4`의 전역 `RequestValidationError` 핸들러가 자동 처리**하므로 별도 `raise` 불필요. Pydantic 쿼리 파라미터 타입 정의만으로 동작 | CLIENT_400 (전역 핸들러 자동) |
| `DB-CONN-001` | PostgreSQL 연결 실패 | FATAL |

**구현 예시 (체이닝 필수)**

```python
# app/services/anomaly_summary.py

from app.core.exceptions import APIError, DBError

async def get_anomaly_summary(db, month: str, grades: list[str]) -> dict:
    try:
        # ... 쿼리 실행
        pass
    except DBError as e:
        raise APIError(
            code="API-INT-001",
            message="이상 요약 집계 중 DB 오류",
            context={"month": month, "grades": grades},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e  # 반드시 from e 명시
```

### 5.2 신규 예외 코드 제안

해당 없음. `exception_spec_vN.md §8` 기존 코드로 처리 가능.

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간, `route_type=3seg`), `banana` (4구간, `route_type=4seg`) — `db_schema_vN.md §commodities` 초기 데이터 기준 |
| 테스트 기간 | 2026-03 기준 월 |
| 특수 케이스 | 이상 0건인 달 → `anomalies: []`, `total_count: 0`, `count_diff` 음수 케이스 |
| **더미 단계 응답 방식** | `frame_spec_backend_vN.md §8.1` 정책 준수 — envelope 고정값(`reference_month: "2026-03"`, `total_count: 0`, `prev_month_count: 0`, `count_diff: 0`) + `anomalies: []` 반환. **fixture 파일 불필요** (§1.3 참조) |
| 더미 → 실제 전환 트리거 | `feat/phase7-stat` dev 머지 완료 후 — `anomaly_results` 테이블에 실제 데이터 적재 확인 시점에 서비스 로직 DB 직접 조회로 전환 |

---

## 7. 완료 기준

**[더미 단계]** `feat/phase7-stat` 머지 전 완료 조건

| 항목 | 기준 |
|------|------|
| 기능 완성 | `GET /api/v1/anomalies/summary` 엔드포인트 더미 기반 200 OK 확인 |
| 출력 형식 | `api_spec_vN.md §GET /anomalies/summary` 응답 필드명·타입 일치, 누락 0개 |
| 더미 고정값 확인 | `reference_month: "2026-03"`, `total_count: 0`, `prev_month_count: 0`, `count_diff: 0`, `anomalies: []` 반환 확인 |
| 이상 0건 케이스 | `anomalies: []` 반환 확인 (null 아님) |
| 예외처리 | `API-VAL-001` — 잘못된 `grade` 값·`month` 형식 입력 시 400 반환 확인 |
| 예외처리 | `API-INT-001` — DB 장애 시 500 반환 (내부 코드 노출 없음) 확인 |
| 필드명 일치 | `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/anomaly.py` 3방향 일치, 불일치 0건 |
| 목업 실행 | 로컬 `uvicorn` 실행 후 `/api/v1/anomalies/summary` 200 OK 오류 없음 |
| 결과 명세 | `docs/results/API-ANO.md` 작성 완료 (더미 단계 결과 기록) |

**[실제 연동 단계]** `feat/phase7-stat` dev 머지 완료 후 추가 완료 조건 (`feature_dev_list_vN §feat/be-api-anomaly` 완료 기준)

| 항목 | 기준 |
|------|------|
| 실제 DB 연동 | 서비스 로직 더미 분기 제거, `anomaly_results` 테이블 실제 조회로 전환 확인 |
| 실제 집계 검증 | `wheat` 또는 `banana` 실제 데이터 기반 `total_count`·`prev_month_count`·`count_diff` 정합성 확인 |
| 실제 200 OK | 실제 DB 데이터 기반 `/api/v1/anomalies/summary` 200 OK 확인 |
| 결과 명세 갱신 | `docs/results/API-ANO.md` 실제 연동 결과 추가 기록 |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| `anomaly_results.id` → `anomaly_id` 외 필드명 임의 변경 | `api_spec_vN.md` 3방향 일치 원칙 위반 |
| `confidence_grade` 값 (`high`, `medium`, `reference`) 외 Literal 임의 추가 | `exception_spec_vN.md` 및 `db_schema_vN.md` 정합성 파괴 |
| `pattern_types`를 응답 필드에 추가 | `api_spec_vN §GET /anomalies/summary` 미명시 필드 — 추가 필요 시 PM 승인 및 api_spec 갱신 선행 필수 |
| `anomalies` 필드 `null` 반환 | `api_spec_vN.md §GET /anomalies/summary` 명세 위반 — 이상 없는 달은 빈 배열 `[]` |
| `from None` 또는 `from e` 생략 예외 raise | `exception_design_vN.md §2.1` 체이닝 추적 불가 |
| `alias_generator` 등 camelCase 변환 적용 | `frame_spec_backend_vN.md §6.1` snake_case 정책 위반 |
| ORM 모델을 엔드포인트 응답으로 직접 반환 | `frame_spec_backend_vN.md §8.13` 직렬화 일관성 파괴 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 데이터 흐름이 `api_spec_vN.md §요약 엔드포인트`와 일치하는가 | ☐ |
| 3방향 필드명 일치 경로가 명시되어 있는가 | ☐ |
| 더미 → 실제 전환 트리거가 `feat/phase7-stat` 완료로 명확히 명시되어 있는가 | ☐ |
| 예외처리 코드가 `exception_spec_vN.md §8` 매핑과 일치하는가 | ☐ |
| `API-ANO-001`이 이 엔드포인트에서 발생하지 않음이 명시되어 있는가 | ☐ |
| 이상 0건 빈 배열 반환 정책이 명시되어 있는가 | ☐ |
| **`pattern_types` 응답 미포함** — `api_spec_vN §GET /anomalies/summary` 미명시 기준으로 제외 확정. 추후 추가 필요 시 api_spec 갱신 선행 필수 | ☑ 확정 |
| **더미 단계 응답 방식** — `frame_spec_backend_vN §8.1` 정책 준수, 빈 배열 고정값 반환으로 확정. fixture 파일 불필요 | ☑ 확정 |
| **fixture 경로** — 더미 응답 방식 확정으로 fixture 파일 불필요. 해당 없음 | ☑ 확정 |

**승인일**: YYYY-MM-DD
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `feat/be-api-anomaly` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-api-anomaly
- **기능 번호**: API-ANO
- **Feature 명세**: `docs/feature_spec_API-ANO_v7.md`
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.

**[더미 단계]**
- [ ] 기능 완성: `GET /api/v1/anomalies/summary` 200 OK (더미 기반)
- [ ] 출력 형식 준수 (응답 필드 누락 0개)
- [ ] 더미 고정값 확인: reference_month, total_count: 0, prev_month_count: 0, count_diff: 0, anomalies: []
- [ ] 이상 0건 케이스: `anomalies: []` 반환 확인 (null 아님)
- [ ] 예외처리 구현 (API-VAL-001, API-INT-001)
- [ ] 목업 실행 성공
- [ ] 결과 명세 `docs/results/API-ANO.md` 작성 (더미 단계)

**[실제 연동 단계]** — `feat/phase7-stat` dev 머지 완료 후 체크
- [ ] 더미 분기 제거 및 실제 DB 조회 전환 확인
- [ ] 실제 데이터 기반 집계 정합성 확인 (wheat 또는 banana)
- [ ] 실제 DB 기반 200 OK 확인
- [ ] 결과 명세 `docs/results/API-ANO.md` 실제 연동 결과 추가

## 필드명 3방향 일치 확인
- [ ] `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/anomaly.py` 필드명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: `API-VAL-001`, `API-INT-001`, `DB-CONN-001`
- 신규 제안 코드: 없음

## 로컬 실행 증빙
{로그·스크린샷·테스트 출력 붙여넣기}

## 리뷰어 확인 요청 사항
- `anomaly_id` 필드명 매핑 (`anomaly_results.id` → 응답 `anomaly_id`) 최종 확인
- 전월 계산 로직 (월 경계 처리) 검토

## 기타
- Phase 7-stat 완료 후 실제 DB 연동 전환 필요 (`feat/phase7-stat` 착수 가능 상태)
- 더미 단계 fixture 파일 없음 (고정값 반환 방식, `frame_spec_backend_vN §8.1` 준수)
```
