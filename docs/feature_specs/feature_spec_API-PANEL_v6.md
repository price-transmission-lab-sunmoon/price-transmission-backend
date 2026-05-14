# Feature 명세서 — 분석 수치 패널 엔드포인트

**문서 유형**: Feature 명세서  
**기능 번호**: `API-PANEL`  
**브랜치명**: `feat/be-api-panel`  
**담당자**: 바게스타니 샤킬라 (백엔드 리드)  
**작성일**: 2026-05-06  
**변경 이력**:
- v1~v4 (2026-05-06): 최초 작성 및 검토·수정
- v5 (2026-05-06): 최종 정리
- v6 (2026-05-11): 참조 문서 버전 갱신 및 오류 수정. §0 `exception_spec_vN.md` v5→v6, `frame_spec_backend_vN.md` v3→v4. §4 `ZSCORE_THRESHOLD_WARNING`→`ZSCORE_WARNING`, `ZSCORE_THRESHOLD_ALERT`→`ZSCORE_ALERT` (`frame_spec_backend_v4 §4` 기준). §5.1 `API-INT-001` 행 추가 (`exception_spec_v6 §8` 매핑 반영). §6 테스트 품목 wheat(4구간)→(3구간), onion→banana(4구간) (`db_schema_v5 §commodities` 기준). §7 예외 코드 카운트 9종→10종.  
**스프린트**: S4 (05.12 ~ 05.19)  
**상태**: 초안 / PM 승인 대기

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.  
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `db_schema_vN.md §anomaly_results, §stat_timeseries, §baselines, §asymmetry_results, §irf_data, §subperiods, §ml_scores, §ml_projections, §cointegration_results` | v5 | 패널 엔드포인트 전체 참조 테이블 구조·컬럼명·FK·조인 조건 | ☐ |
| `api_spec_vN.md §패널 엔드포인트` | v5 | 엔드포인트·request 파라미터·response 필드명 | ☐ |
| `exception_spec_vN.md §API-ANO-001~003, §API-MET-001~003, §API-STR-002, §API-VAL-001` | v6 | 패널 기능에 해당하는 에러 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md` | v3 | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2 디렉토리 구조` | v4 | 파일 생성 위치·서비스 레이어 분할 규칙 확인 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

이상 탐지 결과(`anomaly_results`)에 연결된 통계 수치·ML 판정·판정 경로·IRF·ML 결과맵 데이터를 분석 수치 패널 전용 5개 엔드포인트로 제공한다.

### 1.2 데이터 흐름

```
anomaly_results + stat_timeseries + baselines + asymmetry_results
  + irf_data + subperiods + ml_projections + ml_scores + cointegration_results
  → SQLAlchemy 비동기 쿼리 (anomaly_id 기반 조인)
  → Pydantic 직렬화 (DATE → YYYY-MM 변환)
  → GET /api/v1/anomalies/{anomaly_id}/{detail | stat-series | stat-snapshot | irf | ml-map} JSON 응답
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2 디렉토리 구조` 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/api/v1/endpoints/anomalies.py` | 패널 5개 엔드포인트 라우터 함수 추가 (Frame 단계 더미 상태에서 실 로직으로 교체) |
| 신규 | `app/services/anomaly_panel.py` | 패널 비즈니스 로직 (detail 다중 테이블 조인, stat-series 시계열 조회, stat-snapshot, irf, ml-map). `frame_spec_backend_vN §8.7` 예고명 `anomaly_detail.py`와 다름 — 이 명세 기준 `anomaly_panel.py`로 확정 |
| 수정 | `app/schemas/anomaly.py` | 패널 응답 Pydantic DTO 추가 (`api_spec_vN §패널 엔드포인트` 응답 구조 1:1 구현) |
| 수정 | `app/db/models/anomaly.py` | `baselines`, `irf_data`, `ml_projections`, `ml_scores` ORM 모델 추가 (feat 단계 분할 §8.6) |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | 5개 엔드포인트 실 DB 연결 구현: `/detail` (다중 테이블 조인·`judgment_path` 생성), `/stat-series` (metric 4종 시계열), `/stat-snapshot` (iqr·asymmetry), `/irf` (전체+하위기간), `/ml-map` (model 파라미터 분기) |
| **비구현** | Redis 캐싱 (`feat/be-redis` 브랜치 담당) / `judgment_path` 텍스트 템플릿 최종 문구 확정 (D-04 PM 리뷰 후 반영) / OI-15 `ml-map` `projection_method` 기본값 확정 (S4 내 별도 결정) |
| **선행 조건** | `feat/phase7-ml` 완료 — `ml_scores`·`ml_projections` 테이블 실데이터 적재 필요 |

---

## 2. 입력 데이터

컬럼명·타입은 `db_schema_vN.md` 기준으로 명시한다.

| 출처(테이블) | 사용 컬럼 | 엔드포인트 | 타입 | 비고 |
|-------------|-----------|------------|------|------|
| `anomaly_results` | `id, commodity_id, segment_id, period, pattern_types, primary_pattern, confidence_grade, transmission_rate, zscore_warning, zscore_alert, iqr_outlier, over_transmission, under_transmission, direction_reversal, lag_deviation, pattern1_flag_type, actual_lag, normal_lag, spread_n3_value, pattern3_n, stat_detected, ml_detected, ml_vote, if_anomaly, lof_anomaly, svm_anomaly, subperiod_id, is_new` | `/detail, /stat-series, /stat-snapshot` | 복합 | 패널 헤더 기반. `zscore` 수치 값은 `stat_timeseries.zscore` 참조. `zscore_warning·zscore_alert` 불리언만 이 테이블에서 참조 (D-03) |
| `stat_timeseries` | `period, transmission_rate, rolling_mean, q1, q3, iqr, iqr_lower, iqr_upper, zscore, ect_or_spread, ect_type, in_warmup_period` | `/detail, /stat-series, /stat-snapshot` | NUMERIC, DATE, BOOL | metric별 컬럼 선택. `iqr_lower·iqr_upper`는 `/stat-snapshot?metric=iqr` 응답에 필수 |
| `cointegration_results` | `cointegrated, model_type` | `/detail` (보조) | BOOL, VARCHAR | `/detail` `stat_metrics.cointegrated` 출처 (`db_schema_vN §API 엔드포인트 대응 표` 기준) |
| `baselines` | `normal_transmission_lag, transmission_elasticity, warmup_end, model_type, estimation_start, estimation_end` | `/detail` | SMALLINT, NUMERIC, DATE, VARCHAR | **조인 조건: `subperiod_id IS NULL`** (전체 기간 기준선만, D-15). `normal_transmission_lag` → API 응답 `normal_lag` 매핑. `alpha·wald` 등 비대칭 관련 컬럼은 이 테이블에 없음 — `asymmetry_results` 참조 |
| `asymmetry_results` | `model_type, alpha_plus, alpha_minus, up_coef, down_coef, wald_pvalue, asymmetry_significant, rocket_feather_direction` | `/detail, /stat-snapshot(asymmetry)` | NUMERIC, BOOL, VARCHAR | 구간 A·B 전체 기간 단위만. `up_samples·down_samples`는 DB 컬럼 없음 — `stat_timeseries`에서 국면 구분 집계 후 생성 |
| `irf_data` | `subperiod_id, horizon, irf_downstream, irf_lower_ci, irf_upper_ci, irf_peak_horizon, irf_peak_magnitude` | `/irf` | NUMERIC, SMALLINT | `subperiod_id IS NULL` → 전체 기간 IRF / `NOT NULL` → 하위 기간 IRF. `scope·subperiod_index`는 DB 컬럼 없음 — `scope`는 `subperiod_id` 여부로 백엔드 생성, `subperiod_index`는 `subperiods` 테이블 JOIN 필요. `irf_peak_horizon·irf_peak_magnitude`는 `horizon=0` 행에만 저장 |
| `subperiods` | `id, subperiod_index, period_start, period_end` | `/irf` (보조) | SMALLINT, DATE | `irf_data.subperiod_id` → `subperiods.id` JOIN으로 `subperiod_index`·기간 취득. API 응답 `scope=subperiod` 행의 `label·estimation_start·estimation_end` 생성에 사용 |
| `ml_projections` | `model, projection_method, x_label, y_label, period, x_value, y_value, anomaly_score, is_anomaly, is_highlight` | `/ml-map` | NUMERIC, VARCHAR, BOOL | `model` 파라미터 분기 |
| `ml_scores` | `if_score, if_percentile, lof_score, lof_percentile, svm_score, svm_percentile, ml_detected` | `/detail` (`ml_summary` 필드) | NUMERIC, BOOL | **조인 키: `(commodity_id, segment_id, period)`** — `anomaly_results`와 FK 없음, 직접 조인 필요. `if_anomaly·lof_anomaly·svm_anomaly` 불리언은 `anomaly_results`에서 참조 |
| `breakpoints` | `bp_dates` | `/stat-series (metric=breakpoints)` | DATE[] | D-16 수정 반영: `baselines` 아님 |

### 2.1 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| DB → API 응답 | `DATE` | `YYYY-MM` (str) | Pydantic serializer `strftime("%Y-%m")` |
| DB → API 응답 | `NUMERIC` | `float \| null` | 구간별 미적용 필드는 `null` 반환 (`api_spec_vN §stat_metrics` 적용 구간 표 기준) |
| `metric` 파라미터 → DB 컬럼 매핑 | `metric="ect"` | `ect_or_spread` 컬럼 | 파라미터 값 `'ect'`는 DB 컬럼 `ect_or_spread` 조회로 매핑. Claude Code 구현 시 혼동 방지용 명시 |

---

## 3. 출력 데이터 (API 응답)

### 3.1 구현 엔드포인트 목록

| 엔드포인트 | 설명 | 주 참조 테이블 |
|------------|------|----------------|
| `GET /api/v1/anomalies/{anomaly_id}/detail` | 패널 전체 통합 (통계 수치·ML 판정·판정 경로) | `anomaly_results, baselines, asymmetry_results, ml_scores` (보조: `cointegration_results, stat_timeseries`) |
| `GET /api/v1/anomalies/{anomaly_id}/stat-series` | 지표별 인라인 시계열 (metric 파라미터 분기) | `stat_timeseries, breakpoints.bp_dates` |
| `GET /api/v1/anomalies/{anomaly_id}/stat-snapshot` | 비시계열 지표 스냅샷 (IQR 박스플롯·비대칭 히스토그램) | `stat_timeseries` (iqr), `asymmetry_results` (asymmetry) |
| `GET /api/v1/anomalies/{anomaly_id}/irf` | IRF 차트 데이터 (전체 기간 + 하위 기간별) | `irf_data, subperiods` |
| `GET /api/v1/anomalies/{anomaly_id}/ml-map` | ML 결과맵 2D 투영 데이터 (model 파라미터 필수) | `ml_projections` |

### 3.2 핵심 파라미터 규칙

| 엔드포인트 | 파라미터 | 필수 | 허용값 및 규칙 |
|------------|----------|------|----------------|
| `/stat-series` | `metric` | **필수** | `transmission_rate \| zscore \| ect \| breakpoints` (`iqr·asymmetry` 요청 시 → `SNAPSHOT_METRIC_ON_SERIES` 400) |
| `/stat-series` | `from`, `to` | 선택 | `YYYY-MM`. 기본값: `analysis_start` ~ 최신 기준 월 |
| `/stat-series` | `granularity` | 선택 | `monthly`(기본값) \| `quarterly` \| `yearly` |
| `/stat-snapshot` | `metric` | **필수** | `iqr \| asymmetry` |
| `/irf` | `include_subperiods` | 선택 | 기본값 `true`. 하위 기간 IRF 곡선 + CI 포함 여부 |
| `/ml-map` | `model` | **필수** | `isolation_forest \| lof \| ocsvm` |
| `/ml-map` | `projection_method` | 선택 | `pca` (기본값) \| `feature_direct` ※ OI-15 확정 대기 |

> **`metric` 허용값 관련 주의**: `feature_dev_list_v4`의 `spread` 표기는 오기 — `api_spec_vN` 기준 `breakpoints`가 정확한 4번째 허용값.

---

## 4. 파라미터 제약 조건

> `settings.py`에서 참조해야 하는 파라미터. 이 섹션에 나열된 값은 코드에 **하드코딩하지 않는다**.

| 파라미터명 | `settings.py` 키 | 기본값 | 하드코딩 금지 이유 |
|------------|------------------|--------|-------------------|
| 롤링 윈도우 (IQR 계산) | `ROLLING_WINDOW` | `48` | 로버스트니스 분석 시 36/48/60 전환 필요 |
| Z-score 주의 임계값 | `ZSCORE_WARNING` | `2.0` | 팀 합의 후 settings.py 반영 원칙 |
| Z-score 경보 임계값 | `ZSCORE_ALERT` | `2.5` | 팀 합의 후 settings.py 반영 원칙 |
| ML random seed | `RANDOM_STATE` | `42` | 재현성 확보 |
| ML contamination 범위 (민감도 분석) | `CONTAMINATION_RANGE` | `[0.05, 0.10, 0.15]` | `/ml-map` 점수 산출 기반 파라미터. 민감도 분석 대상으로 하드코딩 금지 |

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스. 이 기능에 해당하는 코드의 발생 조건·처리 방침 확인 시 참조한다. (반복 조회용)
> - **`exception_design_vN.md`**: 에러 체이닝 구현 설계. 실제 코드 작성 시 이 문서의 구현 패턴을 따른다. (코드 구현용)

### 5.1 적용 예외 코드

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `API-ANO-001` | `anomaly_results.id` 미존재 (모든 패널 엔드포인트) | 404 `ANOMALY_NOT_FOUND` / ITEM_SKIP |
| `API-ANO-002` | `anomaly_id`는 있으나 관련 `stat_timeseries` / `baselines` 행 없음 (`/detail, /stat-series, /stat-snapshot`) | 500 `PIPELINE_DATA_MISSING` / 서비스 로직 중단 (API 레이어 예외 — PHASE_SKIP 아님) |
| `API-ANO-003` | `ml_projections` 미산출 (`/ml-map`) | 404 `ML_MAP_NOT_READY` / ITEM_SKIP |
| `API-MET-001` | `metric` 파라미터가 허용 목록 외 (`/stat-series, /stat-snapshot`) | 400 `INVALID_METRIC` / ITEM_SKIP |
| `API-MET-002` | `metric=iqr` 또는 `metric=asymmetry`를 `/stat-series`에 요청 | 400 `SNAPSHOT_METRIC_ON_SERIES` / ITEM_SKIP |
| `API-MET-003` | `metric`이 `iqr/asymmetry` 외를 `/stat-snapshot`에 요청 | 400 `INVALID_METRIC` / ITEM_SKIP |
| `API-STR-002` | `from > to` (`stat-series`의 날짜 파라미터) | 400 `INVALID_DATE_RANGE` / ITEM_SKIP |
| `API-VAL-001` | Pydantic 검증 실패 (필수 파라미터 누락·타입 오류) | 400 / ITEM_SKIP |
| `API-SEG-001` | 유효하지 않은 `segment_id` 참조 (패널 엔드포인트는 `anomaly_id`로 조회하므로 직접 구간 파라미터를 받지 않음 — 단, `anomaly_results.segment_id` 조인 결과가 `segments` 테이블에 없는 경우 적용. `exception_spec_vN §API-SEG-001` 관련 기능에 `feat/be-api-panel` 명시) | 400 `INVALID_SEGMENT` / ITEM_SKIP |
|| `API-INT-001` | 모든 패널 엔드포인트 | 집계 쿼리 실패, 예상치 못한 내부 예외 | CLIENT_500 (`INTERNAL_ERROR`) — 내부 코드 사용자 노출 금지 |

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간), `banana` (4구간) — 구간 커버리지 확인용 |
| 테스트 `anomaly_id` | `feat/phase7-ml` 완료 후 실 DB에서 확인. 더미 단계에서는 `id=1` 고정 사용 |
| 특수 케이스 | 3구간 품목 + `/stat-snapshot?metric=iqr` 요청 / `ml_projections` 미산출 상태 + `/ml-map` 요청 / `metric=asymmetry`를 `/stat-series`에 잘못 요청 |
| 목업 파일 위치 | `tests/fixtures/panel_*.json` |
| 더미 → 실제 전환 트리거 | `feat/phase7-ml` dev 머지 완료 + `VITE_USE_MOCK=false` 전환 후 실 DB 연동으로 전환 |

---

## 7. 완료 기준

> 주관적 판단이 개입되지 않도록 수치·상태로 기술한다.

| 항목 | 기준 |
|------|------|
| 기능 완성 | 5개 엔드포인트 실 DB 데이터 기반 200 OK 확인 (wheat·banana 각 1개씩) |
| 출력 형식 | `api_spec_vN.md §패널 엔드포인트` 응답 필드명·타입 일치, 누락 0개 |
| 에러 케이스 | §5.1 예외 코드 **10종** **각 1건 이상** 테스트 케이스 통과 — `API-ANO-001`(404), `API-ANO-002`(500), `API-ANO-003`(404), `API-MET-001`(400), `API-MET-002`(400), `API-MET-003`(400), `API-STR-002`(400), `API-VAL-001`(400), `API-SEG-001`(400), `API-INT-001`(500) HTTP 상태코드·에러 코드 응답 확인 |
| 파라미터 | §4 파라미터 전체 `settings.py` 참조 확인, 하드코딩 0건 |
| 목업 실행 | §6 기준 로컬 실행 오류 없음 (`feat/phase7-ml` 전에는 더미 응답으로 확인) |
| 3방향 필드 일치 | `db_schema_vN` ↔ `api_spec_vN` ↔ `app/schemas/anomaly.py` Pydantic DTO 필드명 불일치 0건 |
| 결과 명세 | `docs/results/API-PANEL.md` 작성 완료 |
| 후속 선행 조건 | `feat/fe-panel` 착수 가능 상태 (프론트엔드 패널 구현 선행 조건) |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| §4 파라미터 값 코드 하드코딩 (`ROLLING_WINDOW=48` 등) | `settings.py` 단일 관리 원칙 위반 |
| `exception_spec_vN` 미등록 예외 코드 임의 생성 | `exception_spec §사용 규칙` 위반. 신규 상황은 `(proposed)` 표식 후 PM 리뷰 필수 |
| ORM 모델을 endpoint 응답으로 직접 반환 | `frame_spec_backend §8.13` 위반, Pydantic DTO 직렬화 일관성 파괴 |
| API 응답 필드명 camelCase 변환 (`alias_generator`) | 3방향 필드명 일치 원칙 위반 (snake_case 통일) |
| Redis 캐싱 로직 이 브랜치에서 추가 | `feat/be-redis` 브랜치 담당 범위. 이 브랜치는 DB 직접 조회만 구현 |
| `breakpoints` 출처를 `baselines.bp_dates`로 사용 | D-16 수정 — `breakpoints.bp_dates`(DATE[]) 컬럼에서 조회해야 함 |
| `baselines` 조인 시 `subperiod_id IS NULL` 조건 누락 | D-15 — 전체 기간 기준선만 반환해야 함. 조건 누락 시 하위 기간 기준선이 섞여 반환됨 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 5개 엔드포인트가 `api_spec_vN §패널 엔드포인트`와 정합한가 | ☐ |
| §5.1 예외 코드 10종이 `exception_spec_vN`와 일치하는가 | ☐ |
| §4 파라미터가 `settings.py` 참조 원칙을 따르는가 | ☐ |
| 선행 조건(`feat/phase7-ml`)이 S4 내 충족 가능한가 | ☐ |
| OI-15 (`ml-map projection_method`) 미결 사항 인지하는가 | ☐ |

**승인일**: ____________________  
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `feat/be-api-panel` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-api-panel
- **기능 번호**: API-PANEL
- **Feature 명세**: docs/feature_spec_API-PANEL_v6.md
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] 기능 완성: 5개 엔드포인트 (wheat·banana 실 DB 200 OK)
- [ ] 출력 형식 준수 (컬럼 누락 0개)
- [ ] 에러 케이스 10종 각 1건 이상 400/404/500 응답 확인
- [ ] 파라미터 settings.py 참조 확인 (하드코딩 0건)
- [ ] 목업/실 DB 실행 성공
- [ ] 결과 명세 docs/results/API-PANEL.md 작성

## 필드명 3방향 일치 확인
- [ ] db_schema_vN ↔ api_spec_vN ↔ app/schemas/anomaly.py 필드명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: API-ANO-001, API-ANO-002, API-ANO-003, API-MET-001, API-MET-002, API-MET-003, API-STR-002, API-VAL-001, API-SEG-001, API-INT-001
- 신규 제안 코드: {없음 / (proposed) 표식 포함 목록}

## 로컬 실행 증빙
{로그·스크린샷·테스트 출력 붙여넣기}

## 리뷰어 확인 요청 사항
- judgment_path 텍스트 템플릿 최종 문구 (D-04) 승인 요청
- OI-15 (ml-map projection_method) 결정 필요

## 기타
- Redis 캐싱은 feat/be-redis에서 추가 예정
- breakpoints 출처 D-16 수정 반영 확인 (baselines → breakpoints.bp_dates)
- baselines 조인 시 subperiod_id IS NULL 조건 적용 확인 (D-15)
```
