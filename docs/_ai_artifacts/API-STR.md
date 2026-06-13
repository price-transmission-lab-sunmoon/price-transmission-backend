# 구현 결과 명세 — API-STR (시계열 시각화 엔드포인트)

**브랜치**: `feat/be-api-timeseries`
**기능 번호**: `API-STR`
**Feature 명세**: `docs/feature_specs/feature_spec_API-STR_v5.md`
**작성일**: 2026-05-16
**담당자**: 바게스타니 샤킬라

---

## 1. 구현 완료 항목

| 항목 | 상태 | 비고 |
|------|------|------|
| `GET /commodities/{id}/stream` | ✅ 완료 | `app/services/stream.py::get_stream` |
| `GET /commodities/{id}/stream/minimap` | ✅ 완료 | `app/services/stream.py::get_stream_minimap` |
| `GET /commodities/{id}/scatter` | ✅ 완료 | `app/services/scatter.py::get_scatter` |
| `GET /commodities/{id}/raw-prices` | ✅ 완료 | `app/services/raw_prices.py::get_raw_prices` |
| `GET /commodities/{id}/raw-prices/minimap` | ✅ 완료 | `app/services/raw_prices.py::get_raw_prices_minimap` |
| granularity monthly/quarterly/yearly | ✅ 완료 | `_aggregate_monthly_points`, `_aggregate_raw_monthly` |
| 이상 노드 원본 월 단위 반환 | ✅ 완료 | `anomaly_rows` 별도 쿼리, granularity 집계 외 |
| 레이아웃 5 폴백 (3구간 PPI-CPI) | ✅ 완료 | `_resolve_sources` — 3seg layout 5 → `["ppi", "cpi"]` |
| 공통 envelope echo-back | ✅ 완료 | 전 엔드포인트 `requested_from`, `actual_from`, `total_points` 포함 |
| 부분 이탈 클램핑 | ✅ 완료 | `_clamp_range` — `max(from_, analysis_start)` / `min(to_, analysis_end)` |
| `analysis_start/end` date 변환 | ✅ 완료 | `_analysis_dates()` — YYYY-MM str → `date(y, m, 1)` |

---

## 2. 신규 파일 목록

| 파일 | 역할 |
|------|------|
| `app/services/stream.py` | `/stream`, `/stream/minimap` 비즈니스 로직 |
| `app/services/scatter.py` | `/scatter` 비즈니스 로직 |
| `app/services/raw_prices.py` | `/raw-prices`, `/raw-prices/minimap` 비즈니스 로직 + 레이아웃 폴백 |

---

## 3. 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `app/db/models/timeseries.py` | `MvAnomalyDensityYearly` ORM 클래스 추가 (복합 PK, 읽기 전용 뷰) |
| `app/schemas/timeseries.py` | `AnomalyDensityPoint`, `StreamMinimapResponse`, `RawPricesMinimapResponse` 추가 |
| `app/api/v1/endpoints/commodities.py` | 5개 시각화 엔드포인트 → 실 서비스 연결, 쿼리 파라미터 전체 추가 |

---

## 4. 예외처리 구현 현황

| 코드 | 발생 위치 | 처리 내용 |
|------|-----------|-----------|
| `API-COM-001` | `ref_svc.get_commodity_detail` (기존) | 품목 미존재 404 |
| `API-COM-002` | `ref_svc.get_commodity_detail` + `_analysis_dates` | `analysis_start` NULL → 500 `PIPELINE_DATA_MISSING` |
| `API-STR-001` | `stream.py`, `scatter.py`, `raw_prices.py` | warmup 전용 구간 404 `WARMUP_PERIOD_ONLY` |
| `API-STR-002` | `_parse_yyyymm`, `_clamp_range` | 날짜 형식 오류 / from > to → 400 `INVALID_DATE_RANGE` |
| `API-STR-003` | `_clamp_range` | 완전 이탈 범위 → 400 `INVALID_DATE_RANGE` |
| `API-STR-004` | `stream.py`, `raw_prices.py` | 잘못된 granularity → 400 `INVALID_GRANULARITY` |
| `API-STR-005` | `scatter.py` | until > analysis_end → 400 `UNTIL_EXCEEDS_TO` |
| `API-SEG-001` | `stream.py`, `scatter.py` | 없는 구간 요청 → 400 `INVALID_SEGMENT` |
| `API-LAY-001` | `raw_prices.py::_resolve_sources` | layout 1~6 범위 초과 → 400 `INVALID_LAYOUT` |
| `API-LAY-002` | `raw_prices.py::_resolve_sources` | 3구간 + layout 4 → 400 `WHOLESALE_NOT_AVAILABLE` |
| `API-INT-001` | 전 서비스 DB 쿼리 try-except | DB 오류 → 500 `INTERNAL_ERROR` (`from e` 체이닝) |
| `PARSE-DATE-001` | `_safe_period` | DATE→YYYY-MM NULL/오류 → 500 |
| `PARSE-NUM-001` | `_safe_float` | NUMERIC→float 오버플로우 → 500 |

---

## 5. 레이아웃 소스 매핑 (D-12 구현)

| 레이아웃 | 4구간 소스 | 3구간 소스 | 폴백/에러 |
|----------|-----------|-----------|-----------|
| 1 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |
| 2 | intl·import | intl·import | — |
| 3 | import·ppi | import·ppi | — |
| 4 | ppi·wholesale | — | `API-LAY-002` (3구간 → 에러) |
| 5 | wholesale·cpi | ppi·cpi | 자동 폴백 (에러 없음) |
| 6 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |

---

## 6. granularity 집계 규칙

| granularity | 대표 기간 | 집계 방법 |
|-------------|-----------|-----------|
| `monthly` | 각 월 | 원본 그대로 |
| `quarterly` | 분기 마지막 월 (3/6/9/12월) | 해당 분기 3개월 평균 |
| `yearly` | 12월 | 해당 연도 12개월 평균 |

이상 노드(`anomaly_nodes`)는 granularity에 무관하게 **항상 원본 월 단위**로 반환.
집계 포인트에 이상이 포함된 경우 `has_anomaly: true` + `anomaly_ids[]` 포함.

---

## 7. 비구현 항목 (후속 브랜치)

| 항목 | 후속 브랜치 |
|------|-------------|
| Redis TTL 캐싱 (`/stream`, `/raw-prices`) | `feat/be-redis` |
| `/anomalies/{id}/stat-series` | `feat/be-api-panel` |

---

## 8. 필드명 3방향 일치 확인

`db_schema_v5.md` ↔ `api_spec_v5.md` ↔ `app/schemas/timeseries.py` 전체 일치. 불일치 0건.

주요 매핑:
- `anomaly_results.id` → `anomaly_id` (필드명 변환, api_spec §2.3 기준)
- `raw_prices.intl_price_krw_idx` → `RawPriceDataPoint.index_2020`
- `stat_timeseries.period` (DATE) → `YYYY-MM` 문자열 (`_safe_period`)
