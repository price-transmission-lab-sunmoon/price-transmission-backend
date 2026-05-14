# Feature 명세서 — 시계열 시각화 엔드포인트

**문서 유형**: Feature 명세서
**기능 번호**: `API-STR`
**브랜치명**: `feat/be-api-timeseries`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-05-05
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-05-05): 최초 작성
- v2 (2026-05-05): 검토 수정. §2.1 `/scatter` 입력 데이터에 `segments` 테이블 조인(`upstream_label`·`downstream_label` 출처) 누락 추가. §2.2 `granularity` 파라미터 적용 엔드포인트에서 `/scatter` 제거 (`api_spec_vN.md §scatter` — 산점도는 월 단위 고정). §5.1 `API-STR-001` 발생 엔드포인트에 `/scatter` 추가.
- v3 (2026-05-05): 누락 보완. §2.1 `/raw-prices/minimap` 입력 데이터에 `mv_anomaly_density_yearly` 뷰 누락 추가 (`anomaly_density[]` 응답 필드 출처). §1.2 데이터 흐름 `/scatter` 블록과 §3.1 출력 요약 표 보조 참조 테이블에 `segments` 조인 반영.
- v4 (2026-05-05): PM 검토 반영. §1.4 비구현 항목에서 `granularity=quarterly` 제거 → 구현 항목으로 이동 (`api_spec_vN §granularity 동작 규칙`에서 "분기 마지막 월 기준"으로 확정된 사항, §미결 사항에 해당 없음). §2.3 "S6 확정 전까지" 표현 제거. §3.1 `/raw-prices/minimap` 보조 참조 테이블에 `mv_anomaly_density_yearly` 추가. §5.1 `API-COM-002` 추가 (`exception_spec_v6 §8` 반영 — 5개 엔드포인트 전체 발생 가능, `feat/be-api-reference`와 일관성). §7 완료 기준 예외처리 코드 카운트 "9종" → "11종"으로 수정. §10 PR 템플릿 명세서 버전 오기 수정 (`v1` → `v4`).
- v5 (2026-05-11): 참조 문서 버전 갱신. §0 `frame_spec_backend_vN.md` v3 → v4 수정.

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `db_schema_vN.md §stat_timeseries` | v5 | 스트림·산점도 주 테이블 구조·컬럼 | ☐ |
| `db_schema_vN.md §raw_prices` | v5 | 원시 시계열 테이블 구조·컬럼 | ☐ |
| `db_schema_vN.md §anomaly_results` | v5 | 이상 노드 조인 구조 | ☐ |
| `db_schema_vN.md §mv_anomaly_density_yearly` | v5 | 스트림 미니맵·원시 시계열 미니맵 밀도 뷰 구조 | ☐ |
| `db_schema_vN.md §commodities` | v5 | 품목 구간 수(`route_type`) 및 `analysis_start` 출처 | ☐ |
| `db_schema_vN.md §baselines` | v5 | scatter `baseline` 필드 출처 (`transmission_elasticity`, `normal_transmission_lag`) | ☐ |
| `api_spec_vN.md §시각화 엔드포인트` | v5 | 엔드포인트·request·response 필드명 | ☐ |
| `api_spec_vN.md §시계열 공통 쿼리 파라미터` | v5 | `from`, `to`, `granularity` 공통 파라미터 정책 | ☐ |
| `exception_spec_vN.md §2.2, §8` | v6 | 이 기능에 해당하는 에러 코드·처리 방침 | ☐ |
| `exception_design_vN.md §2` | v3 | 에러 체이닝 구현 방식 (`raise X from e` 필수) | ☐ |
| `frame_spec_backend_vN.md §2, §6, §8` | v4 | 프레임 디렉토리 구조·타입 정책·예외 핸들러 정책 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

`stat_timeseries`·`raw_prices`·`anomaly_results`·`mv_anomaly_density_yearly` 테이블을 조회하여 스트림 그래프·미니맵·산점도·원시 시계열 5개 엔드포인트를 구현한다.

### 1.2 데이터 흐름

```
[/stream, /stream/minimap]
stat_timeseries (transmission_rate, upstream_pct, downstream_pct, in_warmup_period)
  + anomaly_results (이상 노드 오버레이)
  + mv_anomaly_density_yearly (미니맵 연도별 밀도, /stream/minimap 전용)
  → SQLAlchemy 비동기 쿼리 (commodity_id, segment_id, period 필터 + granularity 집계)
  → Pydantic 직렬화 (DATE → YYYY-MM, granularity 무관 이상 노드는 원본 월 단위 유지)
  → GET /api/v1/commodities/{id}/stream
  → GET /api/v1/commodities/{id}/stream/minimap

[/scatter]
stat_timeseries (upstream_pct, downstream_pct)
  + anomaly_results (이상 포인트 색상)
  + baselines (transmission_elasticity, normal_transmission_lag — subperiod_id IS NULL)
  + segments (upstream_label, downstream_label — 응답 레이블 출처)
  → SQLAlchemy 비동기 쿼리 (commodity_id, segment_id 필터, 월 단위 고정)
  → GET /api/v1/commodities/{id}/scatter

[/raw-prices, /raw-prices/minimap]
raw_prices (intl_price_krw, import_price_usd, ppi, cpi, wholesale_price + 2020=100 지수)
  + anomaly_results (이상 노드 오버레이)
  + mv_anomaly_density_yearly (미니맵 연도별 밀도, /raw-prices/minimap 전용)
  → layout 파라미터 기반 소스 조합 선택 (레이아웃 1~6, D-12 폴백 정책 적용)
  → SQLAlchemy 비동기 쿼리 + granularity 집계
  → GET /api/v1/commodities/{id}/raw-prices
  → GET /api/v1/commodities/{id}/raw-prices/minimap
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2` 디렉토리 구조 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/api/v1/endpoints/commodities.py` | `/stream`, `/stream/minimap`, `/scatter`, `/raw-prices`, `/raw-prices/minimap` 라우트 핸들러 5개 추가 |
| 수정 | `app/schemas/timeseries.py` | `StreamResponse`, `StreamMinimapResponse`, `ScatterResponse`, `RawPricesResponse`, `RawPricesMinimapResponse` Pydantic 스키마 추가 (Frame에 파일 존재, 내용 추가) |
| 신규 | `app/services/stream.py` | `/stream`, `/stream/minimap` 비즈니스 로직 |
| 신규 | `app/services/scatter.py` | `/scatter` 비즈니스 로직 |
| 신규 | `app/services/raw_prices.py` | `/raw-prices`, `/raw-prices/minimap` 비즈니스 로직 + 레이아웃 폴백 로직 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **스프린트** | S3 (05.05~05.12) (`feature_dev_list_vN.md §feat/be-api-timeseries` 기준) |
| **구현** | `GET /commodities/{id}/stream` — 스트림 그래프 시계열 + 이상 노드 |
| **구현** | `GET /commodities/{id}/stream/minimap` — 전체 기간 yearly 압축 + 연도별 이상 밀도 |
| **구현** | `GET /commodities/{id}/scatter` — 전달 구조 산점도 (월 단위 고정) |
| **구현** | `GET /commodities/{id}/raw-prices` — 원시 시계열 레이아웃 1~6 |
| **구현** | `GET /commodities/{id}/raw-prices/minimap` — 원시 시계열 미니맵 (yearly 고정) |
| **구현** | 시계열 공통 쿼리 파라미터: `from`, `to`, `granularity` (monthly/quarterly/yearly) |
| **구현** | `granularity=quarterly` — 3개월 평균 → 1 포인트, 분기 마지막 월 기준 (`api_spec_vN §granularity 동작 규칙` 확정 사항) |
| **구현** | `from`/`to` 부분 이탈 시 `actual_from`/`actual_to` 클램핑 후 echo |
| **구현** | 레이아웃 5 폴백 — 3구간 품목 요청 시 에러 없이 PPI-CPI(구간 D′)로 자동 전환 (D-12) |
| **비구현** | Redis TTL 캐싱 — `/stream`, `/raw-prices` 캐싱 로직은 `feat/be-redis`에서 추가. 이 브랜치에서는 캐싱 없이 DB 직접 조회 |
| **선행 조건** | `frame/backend` dev 머지 완료 (ORM 모델 9개 포함: `stat_timeseries`, `raw_prices`, `anomaly_results` 등 Frame 단계 정의 완료 상태) |
| **선행 조건** | `feat/phase7-stat` dev 머지 완료 — `stat_timeseries`, `anomaly_results` 실제 데이터 적재 확인 후 실제 DB 조회 가능 |

---

## 2. 입력 데이터

### 2.1 DB 테이블 — 엔드포인트별 사용 컬럼

**`/stream`, `/stream/minimap`**

| 출처 | 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|----------|-----------|------|------|
| DB 테이블 | `stat_timeseries` | `commodity_id`, `segment_id`, `period`, `transmission_rate`, `upstream_pct`, `downstream_pct`, `in_warmup_period` | `db_schema_vN.md §stat_timeseries` 기준 | `UNIQUE (commodity_id, segment_id, period)` |
| DB 테이블 | `anomaly_results` | `id`, `commodity_id`, `segment_id`, `period`, `primary_pattern`, `pattern_types`, `confidence_grade`, `transmission_rate`, `is_new` | `db_schema_vN.md §anomaly_results` 기준 | 이상 노드 오버레이용. `confidence_grade IS NOT NULL` 행만 존재 |
| DB 뷰 | `mv_anomaly_density_yearly` | `commodity_id`, `segment_id`, `year`, `high_count`, `medium_count`, `reference_count` | `db_schema_vN.md §mv_anomaly_density_yearly` 기준 | `/stream/minimap` 전용 |

**`/scatter`**

| 출처 | 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|----------|-----------|------|------|
| DB 테이블 | `stat_timeseries` | `commodity_id`, `segment_id`, `period`, `upstream_pct`, `downstream_pct` | — | 산점도 X·Y축 |
| DB 테이블 | `anomaly_results` | `id`, `commodity_id`, `segment_id`, `period`, `primary_pattern`, `confidence_grade` | — | 이상 포인트 색상·구분 |
| DB 테이블 | `baselines` | `commodity_id`, `segment_id`, `transmission_elasticity`, `normal_transmission_lag` | — | `subperiod_id IS NULL` (전체 기간 기준선, D-15) |
| DB 테이블 | `segments` | `segment_id`, `upstream_label`, `downstream_label` | `VARCHAR(50)` | 응답 `upstream_label`·`downstream_label` 출처 — `db_schema_vN.md §segments` 기준 |

**`/raw-prices`, `/raw-prices/minimap`**

| 출처 | 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|----------|-----------|------|------|
| DB 테이블 | `raw_prices` | `commodity_id`, `period`, `intl_price_krw`, `import_price_usd`, `ppi`, `cpi`, `wholesale_price`, `intl_price_krw_idx`, `import_price_idx`, `ppi_idx`, `cpi_idx`, `wholesale_price_idx` | `db_schema_vN.md §raw_prices` 기준 | 레이아웃별 사용 컬럼 다름 (§3 참조). `wholesale_*`는 4구간 품목만 값 존재 |
| DB 테이블 | `anomaly_results` | `id`, `commodity_id`, `segment_id`, `period`, `primary_pattern`, `confidence_grade`, `is_new` | — | 이상 노드 오버레이용 |
| DB 뷰 | `mv_anomaly_density_yearly` | `commodity_id`, `segment_id`, `year`, `high_count`, `medium_count`, `reference_count` | `db_schema_vN.md §mv_anomaly_density_yearly` 기준 | `/raw-prices/minimap` 전용 — `anomaly_density[]` 응답 필드 출처 |

### 2.2 쿼리 파라미터

| 파라미터 | 적용 엔드포인트 | 타입 | 필수 | 기본값 | 허용 값 |
|----------|---------------|------|:---:|--------|---------|
| `from` | /stream, /scatter, /raw-prices | `YYYY-MM` | — | `analysis_start` | YYYY-MM (zero-pad 필수) |
| `to` | /stream, /scatter, /raw-prices | `YYYY-MM` | — | 최신 기준 월 | YYYY-MM |
| `granularity` | /stream, /raw-prices | string | — | `"monthly"` | `monthly`, `quarterly`, `yearly` |
| `segments` | /stream, /stream/minimap | string | — | 품목 전체 구간 | 콤마 구분 (`A,B,D_prime`) |
| `grade` | /stream, /scatter | string | — | `"high,medium"` | `high`, `medium`, `reference` 콤마 구분 복수 |
| `patterns` | /stream | string | — | `"pattern1,pattern2,pattern3"` | `pattern1`, `pattern2`, `pattern3` 콤마 구분 복수 |
| `segment` | /scatter | string | **필수** | — | `A`, `B`, `C`, `D`, `D_prime` 단일 구간 |
| `until` | /scatter | `YYYY-MM` | — | — | `from` ≤ `until` ≤ `to` |
| `layout` | /raw-prices, /raw-prices/minimap | integer | — | `1` | `1`~`6` |

### 2.3 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| DB → API 응답 | `DATE (YYYY-MM-01)` | `YYYY-MM` 문자열 | Pydantic serializer `strftime("%Y-%m")` |
| DB → API 응답 | `anomaly_results.id` (SERIAL) | `anomaly_id` (integer) | 필드명 매핑 (`id` → `anomaly_id`) |
| 쿼리 파라미터 → 내부 처리 | `YYYY-MM` 문자열 | `date(y, m, 1)` | Pydantic `field_validator` — 월초 정규화 (`frame_spec_backend_vN.md §5`) |
| `granularity=quarterly` | 월 단위 데이터 | 분기 마지막 월 기준 3개월 평균 → 1 포인트 | `api_spec_vN §granularity 동작 규칙` 확정 사항 |
| `granularity=yearly` | 월 단위 데이터 | 연도 12월 기준 12개월 평균 → 1 포인트 | `api_spec_vN §granularity 동작 규칙` |

---

## 3. 출력 데이터

### 3.1 엔드포인트별 API 응답 요약

| 엔드포인트 | 주 참조 테이블 | 보조 참조 테이블 | 핵심 응답 구조 |
|------------|--------------|----------------|---------------|
| `GET /api/v1/commodities/{id}/stream` | `stat_timeseries` | `anomaly_results` | `series[]` (구간별 전이율) + `anomaly_nodes[]` |
| `GET /api/v1/commodities/{id}/stream/minimap` | `mv_anomaly_density_yearly` | `stat_timeseries` | `/stream` 구조 + `anomaly_density[]` (연도별 밀도), `granularity=yearly` 고정 |
| `GET /api/v1/commodities/{id}/scatter` | `stat_timeseries` | `anomaly_results`, `baselines`, `segments` | `points[]` (상류·하류 변화율) + `baseline{}` |
| `GET /api/v1/commodities/{id}/raw-prices` | `raw_prices` | `anomaly_results` | `series[]` (소스별 시계열) + `transmission_overlay[]` + `anomaly_nodes[]` |
| `GET /api/v1/commodities/{id}/raw-prices/minimap` | `raw_prices` | `anomaly_results`, `mv_anomaly_density_yearly` | `/raw-prices` 구조 + `anomaly_density[]`, `granularity=yearly` 고정 |

**시계열 응답 공통 envelope** (`api_spec_vN.md §시계열 응답 공통 envelope` 기준, 모든 엔드포인트 포함 필수)

| 필드 | 타입 | 설명 |
|------|------|------|
| `requested_from` / `requested_to` | `str (YYYY-MM)` | 클라이언트가 요청한 범위 |
| `actual_from` / `actual_to` | `str (YYYY-MM)` | 서버가 실제 반환한 범위 (부분 이탈 시 클램핑) |
| `granularity` | `Literal['monthly','quarterly','yearly']` | 실제 적용된 집계 단위 |
| `total_points` | `int` | 반환된 시계열 포인트 수 |

**이상 노드 반환 정책**: `granularity`에 무관하게 **항상 원본 월 단위로 반환**. 집계 포인트에 이상 포함 시 해당 포인트에 `has_anomaly: true` + `anomaly_ids[]` 함께 포함 (`api_spec_vN.md §granularity 동작 규칙`).

**레이아웃별 소스 조합** (`api_spec_vN.md §raw-prices D-12 폴백 정책` 기준)

| 레이아웃 | 4구간 품목 포함 소스 | 3구간 품목 포함 소스 | 에러 조건 |
|----------|-------------------|-------------------|-----------|
| 1 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |
| 2 | intl·import | intl·import | — |
| 3 | import·ppi | import·ppi | — |
| 4 | ppi·wholesale | — | `WHOLESALE_NOT_AVAILABLE` (3구간 품목) |
| 5 | wholesale·cpi (구간 D) | ppi·cpi (구간 D′, 자동 폴백) | 에러 없음 |
| 6 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |

---

## 4. 파라미터 제약 조건

해당 없음. 이 기능에서 `settings.py` 참조 고정 파라미터는 사용하지 않는다. (`ROLLING_WINDOW` 등은 파이프라인 단계에서 사용하며 이 엔드포인트는 DB에 이미 적재된 결과를 조회만 한다.)

---

## 5. 예외처리

> - **`exception_spec_vN.md §2.2, §8`**: 에러 코드 인덱스 및 기능별 매핑 참조.
> - **`exception_design_vN.md §2`**: 에러 체이닝 구현 방식 (`raise X from e` 필수).

### 5.1 적용 예외 코드

`exception_spec_vN.md §8` 기준 `feat/be-api-timeseries` 구현 필수 코드:
`API-COM-001`, `API-COM-002`, `API-STR-001~005`, `API-SEG-001`, `API-LAY-001~002`, `API-INT-001`, `PARSE-DATE-001`, `PARSE-NUM-001`

| 예외 코드 | 발생 엔드포인트 | 발생 조건 | 처리 방침 |
|-----------|---------------|-----------|-----------|
| `API-COM-001` | 전체 | `commodities.commodity_id` 미존재 | CLIENT_404 |
| `API-COM-002` | 전체 | 품목은 있으나 `analysis_start` NULL (Phase 0 미완) | CLIENT_500 (`PIPELINE_DATA_MISSING`) |
| `API-STR-001` | /stream, /scatter, /raw-prices | 요청 범위 전체가 warmup 기간 내 | CLIENT_404 (`WARMUP_PERIOD_ONLY`) |
| `API-STR-002` | 전체 | `from > to` | CLIENT_400 (`INVALID_DATE_RANGE`) |
| `API-STR-003` | 전체 | `from`/`to`가 `analysis_start`~`analysis_end` **완전** 이탈 | CLIENT_400 (`INVALID_DATE_RANGE`) — 부분 이탈은 클램핑 후 `actual_from`/`actual_to` echo |
| `API-STR-004` | /stream, /raw-prices | `granularity` 값이 `monthly`/`quarterly`/`yearly` 외 | CLIENT_400 (`INVALID_GRANULARITY`) |
| `API-STR-005` | /scatter | `until > to` | CLIENT_400 (`UNTIL_EXCEEDS_TO`) |
| `API-SEG-001` | /stream, /scatter | 품목의 `segments`에 없는 구간 요청 | CLIENT_400 (`INVALID_SEGMENT`) |
| `API-LAY-001` | /raw-prices, /raw-prices/minimap | `layout`이 1~6 밖 | CLIENT_400 (`INVALID_LAYOUT`) |
| `API-LAY-002` | /raw-prices, /raw-prices/minimap | 3구간 품목에 레이아웃 4 요청 | CLIENT_400 (`WHOLESALE_NOT_AVAILABLE`) — **레이아웃 5는 에러 아님, 자동 폴백** |
| `API-INT-001` | 전체 | 집계 쿼리 실패, 예상치 못한 내부 예외 | CLIENT_500 (`INTERNAL_ERROR`) — 내부 코드 사용자 노출 금지 |
| `PARSE-DATE-001` | 전체 | DB `DATE` → `YYYY-MM` 직렬화 실패 (NULL 또는 비정상값) | CLIENT_500 |
| `PARSE-NUM-001` | 전체 | DB `NUMERIC` → Python `float` 오버플로우 | CLIENT_500 |

**구현 예시 (체이닝 필수)**

```python
# app/services/stream.py

from app.core.exceptions import APIError, DBError

async def get_stream(db, commodity_id: str, ...) -> dict:
    try:
        # ... 쿼리 실행
        pass
    except DBError as e:
        raise APIError(
            code="API-INT-001",
            message="스트림 시계열 조회 중 DB 오류",
            context={"commodity_id": commodity_id},
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
| 테스트 기간 | 2020-01 ~ 2026-03 (실제 데이터 기준) |
| 특수 케이스 1 | warmup 기간(`in_warmup_period=true`) 포함 요청 → `actual_from` 클램핑 또는 `WARMUP_PERIOD_ONLY` 404 |
| 특수 케이스 2 | 3구간 품목(`wheat`)에 레이아웃 4 요청 → `WHOLESALE_NOT_AVAILABLE` 400 |
| 특수 케이스 3 | 3구간 품목(`wheat`)에 레이아웃 5 요청 → 에러 없이 PPI-CPI 자동 폴백 응답 |
| 특수 케이스 4 | `from > to` 요청 → `INVALID_DATE_RANGE` 400 |
| 특수 케이스 5 | 4구간 품목(`banana`)에 레이아웃 4·5·6 요청 → 정상 도매가 포함 응답 |
| 특수 케이스 6 | `granularity=yearly` — 전체 기간 26포인트 연별 집계 응답 |
| 실제 데이터 전환 트리거 | `feat/phase7-stat` dev 머지 완료 후 — `stat_timeseries`, `anomaly_results` 실제 데이터 적재 확인 시점에 DB 직접 조회로 동작 (별도 더미 분기 불필요 — 이 기능은 실제 데이터 기반으로만 동작함) |

---

## 7. 완료 기준

| 항목 | 기준 |
|------|------|
| 기능 완성 | 5개 엔드포인트 실제 DB 데이터 기반 200 OK 확인 (`feature_dev_list_vN §feat/be-api-timeseries`) |
| 구간 커버리지 | 3구간 품목(`wheat`) + 4구간 품목(`banana`) 각 1개씩 실제 시계열 반환 확인 |
| granularity | `monthly`/`quarterly`/`yearly` 3종 동작 확인 (/stream, /raw-prices 각각) |
| 이상 노드 정책 | `granularity` 집계 무관 이상 노드 원본 월 단위 반환 확인 |
| 레이아웃 폴백 | 3구간 품목 레이아웃 5 요청 시 에러 없이 PPI-CPI 응답 확인 |
| 공통 envelope | `requested_from`, `actual_from`, `granularity`, `total_points` 전 엔드포인트 포함 확인 |
| 클램핑 | 부분 이탈 `from`/`to` 요청 시 `actual_from`/`actual_to` 클램핑 echo 확인 |
| 예외처리 | `exception_spec_vN.md §8` 매핑 에러 코드 **11종** (`API-COM-001`, `API-COM-002`, `API-STR-001~005`, `API-SEG-001`, `API-LAY-001~002`, `API-INT-001`) + **2종 파싱 에러** (`PARSE-DATE-001`, `PARSE-NUM-001`) 구현 및 400/404/500 응답 형식 확인 |
| 필드명 일치 | `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/timeseries.py` 3방향 일치, 불일치 0건 |
| 로컬 실행 | `uvicorn` 실행 후 5개 엔드포인트 200 OK 오류 없음 |
| 결과 명세 | `docs/results/API-STR.md` 작성 완료 |
| 후속 선행 조건 | `feat/be-api-panel` 착수 가능 상태 (`feat/phase7-ml` 완료 후) |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| 레이아웃 5 요청 시 `WHOLESALE_NOT_AVAILABLE` 반환 | `api_spec_vN.md §D-12` 폴백 정책 위반 — 레이아웃 5는 3구간 품목에서 에러 없이 PPI-CPI 자동 폴백 |
| `anomaly_results.id` → `anomaly_id` 외 필드명 임의 변경 | `api_spec_vN.md` 3방향 일치 원칙 위반 |
| `alias_generator` 등 camelCase 변환 적용 | `frame_spec_backend_vN.md §6.1` snake_case 정책 위반 |
| ORM 모델을 엔드포인트 응답으로 직접 반환 | `frame_spec_backend_vN.md §8.13` 직렬화 일관성 파괴 |
| `from None` 또는 `from e` 생략 예외 raise | `exception_design_vN.md §2.1` 체이닝 추적 불가 |
| `/stream`, `/raw-prices`에 Redis 캐싱 로직 추가 | 캐싱은 `feat/be-redis` 전담 — 이 브랜치에서는 DB 직접 조회만 |
| `baselines`에서 `subperiod_id IS NOT NULL` 행 사용 | `/scatter` `baseline` 필드는 전체 기간 기준선(`subperiod_id IS NULL`)만 반환 (D-15) |
| `granularity` 값 임의 추가 (`monthly`/`quarterly`/`yearly` 외 Literal 추가) | `frame_spec_backend_vN.md §6.2` Literal 일치 원칙 위반 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 데이터 흐름이 `api_spec_vN.md §시각화 엔드포인트`와 일치하는가 | ☐ |
| 5개 엔드포인트 주 참조 테이블·보조 참조 테이블이 `db_schema_vN.md §API 엔드포인트 ↔ 테이블 대응`과 일치하는가 | ☐ |
| 레이아웃 폴백 정책 (D-12) — 레이아웃 4만 에러, 레이아웃 5는 자동 폴백 — 이 명시되어 있는가 | ☐ |
| 이상 노드 원본 월 단위 반환 정책이 명시되어 있는가 | ☐ |
| 부분 이탈 클램핑 vs 완전 이탈 에러 구분이 명시되어 있는가 | ☐ |
| 예외처리 코드가 `exception_spec_vN.md §8` 매핑과 일치하는가 (`API-COM-002` 포함) | ☐ |
| 3방향 필드명 일치 경로가 명시되어 있는가 | ☐ |
| Redis 캐싱 비구현 범위가 명확히 명시되어 있는가 | ☐ |
| `baselines` 전체 기간 기준선 선택 규칙 (D-15)이 명시되어 있는가 | ☐ |
| `granularity=quarterly` 분기 마지막 월 기준이 `api_spec_vN §granularity 동작 규칙` 확정 사항으로 명시되어 있는가 | ☐ |

**승인일**: YYYY-MM-DD
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `feat/be-api-timeseries` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-api-timeseries
- **기능 번호**: API-STR
- **Feature 명세**: `docs/feature_spec_API-STR_v5.md`
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] 5개 엔드포인트 실제 DB 데이터 기반 200 OK 확인
- [ ] 3구간·4구간 품목 각 1개씩 실제 시계열 반환 확인
- [ ] granularity 3종 동작 확인 (monthly/quarterly/yearly)
- [ ] 이상 노드 원본 월 단위 반환 확인 (granularity 무관)
- [ ] 레이아웃 5 폴백 — 3구간 품목 에러 없이 PPI-CPI 자동 응답 확인
- [ ] 공통 envelope 전 엔드포인트 포함 확인
- [ ] 부분 이탈 클램핑 → `actual_from`/`actual_to` echo 확인
- [ ] 예외처리 구현 (API-COM-001, API-COM-002, API-STR-001~005, API-SEG-001, API-LAY-001~002, API-INT-001, PARSE-DATE-001, PARSE-NUM-001)
- [ ] 로컬 실행 성공
- [ ] 결과 명세 `docs/results/API-STR.md` 작성

## 필드명 3방향 일치 확인
- [ ] `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/timeseries.py` 필드명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: `API-COM-001`, `API-COM-002`, `API-STR-001`, `API-STR-002`, `API-STR-003`, `API-STR-004`, `API-STR-005`, `API-SEG-001`, `API-LAY-001`, `API-LAY-002`, `API-INT-001`, `PARSE-DATE-001`, `PARSE-NUM-001`
- 신규 제안 코드: 없음

## 로컬 실행 증빙
{로그·스크린샷·테스트 출력 붙여넣기}

## 리뷰어 확인 요청 사항
- 레이아웃 5 폴백 로직 (`app/services/raw_prices.py`) 검토
- `baselines` 전체 기간 기준선 쿼리 (`subperiod_id IS NULL`) 확인
- `granularity=quarterly` 분기 마지막 월 기준 집계 로직 검토

## 기타
- `/stream`, `/raw-prices` Redis 캐싱은 `feat/be-redis`에서 추가 예정
- `feat/be-api-panel` 착수 가능 상태 (`feat/phase7-ml` 완료 후)
```
