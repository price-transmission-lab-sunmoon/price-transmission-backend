# Feature 명세서 — 파이프라인 결과 DB 적재

**문서 유형**: Feature 명세서  
**기능 번호**: `DB-PIPELINE`  
**브랜치명**: `feat/be-db-pipeline`  
**담당자**: 바게스타니 샤킬라 (백엔드 리드)  
**작성일**: 2026-05-07  
**변경 이력**:
- v1 (2026-05-07): 최초 작성
- v2 (2026-05-11): 참조 문서 버전 갱신 및 오류 수정. §0 `exception_spec_vN.md` v5→v6, `frame_spec_backend_vN.md` v3→v4. §6 테스트 품목 wheat (4구간)→(3구간), banana (3구간)→(4구간) (`db_schema_v5` 실제 시드 레코드 기준).  
**스프린트**: S3 (05.05 ~ 05.12)  
**상태**: 초안 / PM 승인 대기

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.  
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `pipeline_output_spec_vN.md §Phase 2~6 출력 파일` | v7 | 입력 CSV/JSON 파일 경로·컬럼명·타입 | ☐ |
| `db_schema_vN.md §stationarity_results ~ §subperiods` | v5 | 적재 테이블 구조·UNIQUE 키·FK·필터 조건 전체 | ☐ |
| `db_schema_vN.md §설계 원칙 §D-02·D-11·D-17` | v5 | 탐지 이벤트만 적재·월초 검증·Phase 롤백 정책 | ☐ |
| `exception_spec_vN.md §DB-CONN-001~002, §DB-TX-001, §DB-UNIQ-001~003, §DB-FK-001~003, §DB-TYPE-001~002, §DB-NN-001~002, §DB-ARR-001~002, §DB-RUN-001, §PARSE-DATE-001, §PARSE-ARR-001, §PARSE-ENUM-001` | v6 | 이 기능에 해당하는 에러 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md` | v3 | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2 디렉토리 구조, §8.6 ORM 모델 분할` | v4 | 파일 생성 위치·ORM 모델 분할 범위 확인 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

Phase 2~6 파이프라인 CSV/JSON 출력 파일을 읽어 해당 DB 테이블에 UPSERT로 적재하고, 신규 Alembic migration을 수동 작성하여 `db_schema_vN §Phase 2~6 계량 테이블` 10개를 생성한다.

### 1.2 데이터 흐름

```
data/processed/phase2/stationarity_results.csv         → stationarity_results  (Phase 2)
data/processed/phase3/cointegration_results.csv        → cointegration_results (Phase 3)
data/processed/phase3/model_routing.json               → cointegration_results.granger_direction 갱신용 (Phase 5)
data/processed/phase4/baseline/{cid}_{seg}_*.json      → baselines             (Phase 4)
data/processed/phase4/irf/{cid}_{seg}_irf.csv          → irf_data              (Phase 4)
data/processed/phase4/model_params/{cid}_{seg}_*.json  → model_params          (Phase 4)
data/processed/phase5/granger_results.csv             → granger_results       (Phase 5)
data/processed/phase6/breakpoints/{cid}_{seg}_*.json   → breakpoints (bp_dates·Chow 컬럼) + subperiods (Phase 6, JSON 내 chow_test_points·subperiods 배열 포함)
  → SQLAlchemy 비동기 UPSERT (단일 Phase 트랜잭션)
  → pipeline_runs 적재 이력 기록
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2 디렉토리 구조` 및 `§8.6 ORM 모델 분할` 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 신규 | `alembic/versions/0003_phase2_3_tables.py` | `stationarity_results`, `cointegration_results` 테이블 + 인덱스 |
| 신규 | `alembic/versions/0004_phase4_5_tables.py` | `model_params`, `irf_data`, `baselines`, `granger_results` 테이블 + 인덱스 |
| 신규 | `alembic/versions/0005_phase6_tables.py` | `breakpoints`, `subperiods` 테이블 + 인덱스 |
| 신규 | `app/db/models/phase2_3.py` | `stationarity_results`, `cointegration_results` ORM 모델 (`frame_spec §8.6` 분할 파일명 기준 — `feat/pipeline-phase2-3` 예고명과 이 브랜치명 `feat/be-db-pipeline` 불일치로 PM 확인 필요, §9 참조) |
| 신규 | `app/db/models/phase4_5.py` | `model_params`, `irf_data`, `baselines`, `granger_results` ORM 모델 (`frame_spec §8.6` 분할 기준) |
| 신규 | `app/db/models/phase6.py` | `breakpoints`, `subperiods` ORM 모델 (`frame_spec §8.6` 분할 기준) |
| 신규 | `app/db/loader/` | Phase별 적재 스크립트 디렉토리 |
| 신규 | `app/db/loader/base.py` | `pipeline_runs` 기록·트랜잭션 공통 유틸리티 |
| 신규 | `app/db/loader/phase2.py` | `stationarity_results` 적재 로직 |
| 신규 | `app/db/loader/phase3.py` | `cointegration_results` 적재 로직 |
| 신규 | `app/db/loader/phase4.py` | `model_params`, `irf_data`, `baselines` 적재 로직 |
| 신규 | `app/db/loader/phase5.py` | `granger_results` + `cointegration_results.granger_direction` 갱신 |
| 신규 | `app/db/loader/phase6.py` | `breakpoints`, `subperiods` 적재 로직 |
| 신규 | `app/db/loader/runner.py` | Phase 2→3→4→5→6 순차 실행 진입점 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | Alembic revision 3개 (Phase 2~3·4~5·6 테이블) 수동 작성 / Phase 2~6 적재 스크립트 / `pipeline_runs` 적재 이력 기록 / Phase 단위 트랜잭션·롤백 / `period.day == 1` 검증 (D-11) |
| **비구현** | Phase 7·7-ML·8 테이블 (`feat/phase7-*` 브랜치 담당) / Phase 0~1 원시 시계열 적재 (`raw_prices` 테이블은 Frame 포함이나 적재 스크립트는 별도 브랜치) / Redis 캐시 무효화 트리거 (`feat/be-redis` 담당) |
| **선행 조건** | `frame/backend` dev 머지 완료 (이미 충족 — Frame 커밋 완료 상태) / Phase 2~3 출력 CSV·JSON 파일 존재 (`data/processed/phase2/`, `data/processed/phase3/`) |
| **후속 조건** | `feat/be-api-timeseries`, `feat/be-api-panel` 착수 가능 (실 DB 데이터 의존) / `feat/be-redis` 착수 가능 |

---

## 2. 입력 데이터

컬럼명·타입은 `pipeline_output_spec_vN.md` 기준으로 명시한다.

| 출처 | 파일명 | 주요 컬럼 | 타입 | 비고 |
|------|--------|-----------|------|------|
| Phase 2 | `phase2/stationarity_results.csv` | `commodity_id`, `column` (→ DB `price_col`), `n_obs`, `level_adf_stat`, `level_adf_pvalue`, `level_adf_lags`, `level_adf_stationary`, `level_kpss_stat`, `level_kpss_pvalue`, `level_kpss_stationary`, `level_judgment`, `level_conflict_note`, `diff_adf_stat`, `diff_adf_pvalue`, `diff_kpss_stat`, `diff_kpss_pvalue`, `diff_judgment`, `integration_order`, `i2_flag` | str, float, int, bool | `pipeline_output_spec_vN §Phase 2 stationarity_results.csv` 기준. `column` → DB `price_col` 컬럼명 매핑 주의. `integration_orders.json`은 Phase 3 입력 전달용 파일이며 DB 적재 대상 아님 |
| Phase 3 | `phase3/cointegration_results.csv` | `commodity_id`, `segment` (→ DB `segment_id`), `upstream` (→ DB `upstream_col`), `downstream` (→ DB `downstream_col`), `n_obs`, `var_lag_aic`, `var_lag_bic`, `johansen_lag`, `trace_stat_r0`, `trace_crit_r0`, `trace_reject_r0`, `eigen_stat_r0`, `eigen_crit_r0`, `eigen_reject_r0`, `cointegrated`, `judgment_note`, `model_selected` (→ DB `model_type`), `integration_flag` | str, float, int, bool | `pipeline_output_spec_vN §Phase 3 cointegration_results.csv` 기준. **컬럼명 매핑 주의**: `segment`→`segment_id`, `upstream`→`upstream_col`, `downstream`→`downstream_col`, `model_selected`→`model_type`. `var_lag_bic`는 DB `cointegration_results`에 없음 — 적재 제외. **DB 전용 컬럼(파이프라인 파일에 없음) 처리**: `upstream_integration_order`·`downstream_integration_order` → `stationarity_results` JOIN 후 채움 / `integration_order_match` → 두 값 비교 후 생성 / `coint_tested` → I(1) 쌍 여부 로직으로 생성 (기본 `False`) / `trace_stat`·`trace_pvalue`·`maxeig_stat`·`maxeig_pvalue`·`coint_rank` → `trace_stat_r0`·`trace_crit_r0`·`eigen_stat_r0`·`eigen_crit_r0` 에서 파생 (DB에 `trace_pvalue`·`maxeig_pvalue` 컬럼 실존 — Johansen 라이브러리는 p값을 제공하지 않으므로 `None`/`NULL` 적재) / `granger_direction` → Phase 5 적재 시 UPDATE로 채움 (초기 `NULL`) |
| Phase 4 | `phase4/model_params/{cid}_{seg}_model.json` | `commodity_id`, `segment` (→ DB `segment_id`), `model_type`, `lag_selected` (→ DB `lag_selected`), `lag_selection_criterion` (→ DB `lag_criterion`), `n_obs`, `estimation_period_start` (→ DB `estimation_start`), `estimation_period_end` (→ DB `estimation_end`), `aic`, `bic`, `log_likelihood`, `cointegrated`, `coint_rank`, `det_order` | str, int, float, bool | 전체 기간 + 하위 기간별 각 1파일. **필드명 매핑 주의**: `segment`→`segment_id`, `lag_selection_criterion`→`lag_criterion`, `estimation_period_start`→`estimation_start`, `estimation_period_end`→`estimation_end` (파이프라인 JSON 키명과 DB 컬럼명 상이). VECM에만 `alpha`·`beta` 포함 — DB 적재 대상 아님 |
| Phase 4 | `phase4/irf/{cid}_{seg}_irf.csv` | `horizon`, `irf_downstream`, `irf_lower_ci`, `irf_upper_ci`, `irf_peak_horizon`, `irf_peak_magnitude` | int, float | `pipeline_output_spec_vN §irf.csv` 기준. 파이프라인 파일에서는 `irf_peak_horizon`·`irf_peak_magnitude`가 **모든 행에 동일값**으로 출력됨. DB 적재 시 `horizon=0` 행에만 저장하고 나머지 행의 peak 값은 무시 (`db_schema_vN §irf_data` 기준) |
| Phase 4 | `phase4/baseline/{cid}_{seg}_baseline.json` | `commodity_id`, `segment` (→ DB `segment_id`), `normal_transmission_lag`, `transmission_elasticity`, `warmup_end`, `model_type`, `estimation_period_start` (→ DB `estimation_start`), `estimation_period_end` (→ DB `estimation_end`), `n_obs` | str, int, float, date | **필드명 매핑 주의**: `segment`→`segment_id`, `estimation_period_start`→`estimation_start`, `estimation_period_end`→`estimation_end` (파이프라인 JSON 키명과 DB 컬럼명 상이). `warmup_end = estimation_period_start + 48개월` 검증 (D-06) |
| Phase 5 | `phase5/granger_results.csv` | `commodity_id`, `segment` (→ DB `segment_id`), `direction`, `max_lag`, `best_lag`, `f_stat`, `pvalue`, `significant`, `confirmed_direction` | str, int, float, bool | `pipeline_output_spec_vN §Phase 5 granger_results.csv` 기준. 4구간 품목(groundnuts·banana·orange) 구간 C만 존재. 단일 통합 파일 (품목·구간별 개별 파일 아님). `segment`→DB `segment_id` 매핑. `direction`: `'ppi_to_wholesale'\|'wholesale_to_ppi'` (2행/품목). `best_lag`은 DB `granger_results`에 없음 — 적재 제외 |
| Phase 6 | `phase6/breakpoints/{cid}_{seg}_breakpoints.json` | `commodity_id`, `segment` (→ DB `segment_id`), `borderline_cointegration`, `bai_perron_breakpoints` (→ DB `bp_dates` DATE[]), `bai_perron_best_k` (→ DB `bp_best_k`), `bic_scores` (→ DB `bic_scores` JSONB), `chow_test_points["2008-01"].f_stat` (→ `chow_2008_f`), `chow_test_points["2008-01"].pvalue` (→ `chow_2008_pvalue`), `chow_test_points["2008-01"].significant` (→ `chow_2008_sig`), 동일하게 `2020-01`·`2022-01`, `subperiods[].id` (→ `subperiod_index`), `subperiods[].start` (→ `period_start` DATE), `subperiods[].end` (→ `period_end` DATE), `subperiods[].n_obs`, `subperiods[].merged_with` (→ `merged_with_index`) | str, float, bool, list | **JSON → DB 변환 주의**: `bai_perron_breakpoints` 문자열 배열 `"YYYY-MM"` → DATE[] `"YYYY-MM-01"` 월초 승격 / `chow_test_points` 키 `"2008-01"·"2020-01"·"2022-01"` 항상 존재 (D-07 고정 3개 시점) / `subperiods[].merged_with` 값은 `id` 아닌 `subperiod_index` 기준으로 적재 / Chow Test 컬럼은 `db_schema_vN §breakpoints chow_2008_*·chow_2020_*·chow_2022_*` 구조에 1:1 대응 / `subperiods` 테이블에 `n_obs`·`merged_with_index` 별도 적재 |

### 2.1 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| 파이프라인 → DB 적재 | `DatetimeIndex (MS)` | `DATE (YYYY-MM-01)` | `period.day == 1` 검증 후 저장 (D-11). 실패 시 `DB-TYPE-001` FATAL |
| 파이프라인 → DB 적재 | `str "YYYY-MM"` | `DATE (YYYY-MM-01)` | 파싱 후 `day=1` 정규화. 실패 시 `DB-TYPE-001` |
| 파이프라인 → DB 적재 | `list[str]` (bp_dates) | `DATE[]` | PostgreSQL DATE 배열. 파싱 실패 시 `DB-ARR-002` WARN — NULL 적재 (D-07) |
| 파이프라인 → DB 적재 | `subperiods[].merged_with` (JSON 정수, id 기준) | `subperiods.merged_with_index` (SMALLINT, index 기준) | JSON `merged_with` 값은 `subperiod.id` 아닌 `subperiod_index` 로 해석하여 적재 (D-07 변환 규칙) |
| 파이프라인 → DB 적재 | `str` (model_type, granger_direction 등) | `VARCHAR` Literal | Pydantic `Literal` 검증. 범위 밖이면 `PARSE-ENUM-001` CLIENT_500 |

---

## 3. 출력 데이터 (DB 적재)

### 3.1 Alembic Migration 목록

| Revision 파일 | 생성 테이블 | autogenerate 사용 여부 |
|---|---|---|
| `0003_phase2_3_tables.py` | `stationarity_results`, `cointegration_results` | **금지** — 수동 작성 (`frame_spec §8.9`) |
| `0004_phase4_5_tables.py` | `model_params`, `irf_data`, `baselines`, `granger_results` | **금지** — 수동 작성 |
| `0005_phase6_tables.py` | `breakpoints` (`bp_dates DATE[]`, `chow_2008_*·chow_2020_*·chow_2022_*` Chow 컬럼 9개 포함), `subperiods` | **금지** — 수동 작성 |

### 3.2 DB 적재 대상

**적재 방식 정의**
- **UPSERT**: UNIQUE 키 충돌 시 갱신 (`ON CONFLICT DO UPDATE`) — 표준 경로
- **UPSERT (FK 후보정)**: `subperiod_id` FK 참조 대상 미존재 시 `NULL` 적재 후 Phase 6 완료 후 보정

| DB 테이블 | UNIQUE 키 | 필터 조건 | 적재 방식 | 트랜잭션 단위 |
|-----------|-----------|-----------|-----------|---------------|
| `stationarity_results` | `(commodity_id, price_col)` | 전체 행 | UPSERT | Phase 2 단일 트랜잭션 |
| `cointegration_results` | `(commodity_id, segment_id)` | 전체 행 | UPSERT | Phase 3 단일 트랜잭션 |
| `cointegration_results.granger_direction` | — | 4구간 품목 구간 C만 | UPDATE | Phase 5 단일 트랜잭션 |
| `model_params` | `(commodity_id, segment_id, subperiod_id)` | 전체 행 | UPSERT | Phase 4 단일 트랜잭션 |
| `irf_data` | `(commodity_id, segment_id, subperiod_id, horizon)` | 전체 행 | UPSERT | Phase 4 단일 트랜잭션 |
| `baselines` | `(commodity_id, segment_id, subperiod_id)` | 전체 행 | UPSERT | Phase 4 단일 트랜잭션 |
| `granger_results` | `(commodity_id, segment_id, direction)` | 4구간 품목 구간 C만 | UPSERT | Phase 5 단일 트랜잭션 |
| `breakpoints` | `(commodity_id, segment_id)` | 전체 행 | UPSERT | Phase 6 단일 트랜잭션 |
| `subperiods` | `(commodity_id, segment_id, subperiod_index)` | 전체 행 | UPSERT | Phase 6 단일 트랜잭션 |
| `pipeline_runs` | `(run_date)` | — | INSERT | 적재 시작 시·완료 시·실패 시 각 1회 |
| `data_freshness` | — (항상 최신 1개 행 유지) | — | UPSERT | Phase 전체 완료(`status='completed'`) 후 `data_up_to`·`next_run_date` 갱신. `pipeline_run_id` FK 설정 |

> **Phase 4 `subperiod_id` 처리**: Phase 6 완료 전에는 `subperiods` 테이블이 없어 `subperiod_id IS NULL` (전체 기간) 행만 적재한다. Phase 6 완료 후 재실행 시 하위 기간 행을 추가 적재한다.

### 3.3 `pipeline_runs` 기록 규칙

| 이벤트 | `status` 값 | 기록 시점 |
|--------|-------------|-----------|
| 적재 시작 | `'running'` | `runner.py` 실행 직후 |
| 전 Phase 완료 | `'completed'` | Phase 6 적재 성공 후 |
| 특정 Phase 실패 | `'failed'` | `DB-TX-001` 롤백 직후 |

`pipeline_runs`에 `phases_run VARCHAR(10)[]` 배열로 완료된 Phase 번호를 누적 기록한다 (`db_schema_vN §pipeline_runs` 기준 — 컬럼 실존 확인). 재실행 시 마지막 `completed` Phase부터 재시작한다 (D-17).

---

## 4. 파라미터 제약 조건

> `settings.py`에서 참조해야 하는 파라미터. 이 섹션에 나열된 값은 코드에 **하드코딩하지 않는다**.

| 파라미터명 | `settings.py` 키 | 기본값 | 하드코딩 금지 이유 |
|------------|------------------|--------|-------------------|
| 파이프라인 출력 루트 디렉토리 | `PIPELINE_DATA_ROOT` ⚠️ 신규 키 | `"data/processed"` | 배포 환경별 경로 변경 가능. `frame_spec §4` 미등록 — PM 승인 후 `settings.py` 추가 (§9 참조) |
| 롤링 윈도우 (warmup 계산) | `ROLLING_WINDOW` | `48` | `warmup_end = estimation_start + 48개월` 검증 시 참조 (`frame_spec §4` 등록 키) |
| DB 커넥션 풀 크기 | `DB_POOL_SIZE` ⚠️ 신규 키 | `10` | `frame_spec_backend §5 pool_size=10`과 중복 관리 방지. PM 승인 후 추가 (§9 참조) |

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스. 이 기능에 해당하는 코드의 발생 조건·처리 방침 확인 시 참조한다. (반복 조회용)
> - **`exception_design_vN.md`**: 에러 체이닝 구현 방식. 실제 코드 작성 시 이 문서의 구현 패턴을 따른다. (코드 구현용)

### 5.1 적용 예외 코드

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `DB-CONN-001` | PostgreSQL 연결 실패 | FATAL — `pipeline_runs.status='failed'` 기록 |
| `DB-CONN-002` | SQLAlchemy 커넥션 풀 고갈 | RETRY 3회 (지수 백오프 1s/2s/4s) → 실패 시 `DB-CONN-001` 승격 |
| `DB-TX-001` | Phase 적재 중 예외 발생 (ORM 롤백) | 해당 Phase 전체 롤백. 다음 Phase 실행 중단. `pipeline_runs.phases_run`에 해당 Phase 미기록 |
| `DB-UNIQ-001` | `raw_prices` UNIQUE 위반 | UPSERT (`ON CONFLICT DO UPDATE`) |
| `DB-UNIQ-002` | `anomaly_results` UNIQUE 위반 | UPSERT (이 브랜치에서는 `anomaly_results` 미적재이나 핸들러 등록 필요) |
| `DB-UNIQ-003` | `stat_timeseries` UNIQUE 위반 | UPSERT |
| `DB-FK-001` | `commodities`에 없는 `commodity_id` 참조 | FATAL — 시드 적재 누락 의심, 재시드 후 재실행 |
| `DB-FK-002` | `segments`에 없는 `segment_id` 참조 | FATAL |
| `DB-FK-003` | `subperiod_id` 참조 대상 `subperiods` 미존재 | WARN — `NULL`로 적재. Phase 6 적재 완료 후 후보정 배치 |
| `DB-TYPE-001` | `period` 값이 월초(`YYYY-MM-01`)가 아님 | FATAL — D-11 위반. 입력 정규화 레이어 버그 |
| `DB-TYPE-002` | `NUMERIC(precision, scale)` 자릿수 초과 | FATAL — 스키마 precision 재검토 필요 |
| `DB-NN-001` | `anomaly_results.confidence_grade` NULL 시도 | FATAL — D-02 위반. **이 브랜치에서 `anomaly_results` 미적재이나 핸들러 등록 필요** (feat/phase7 연계) |
| `DB-NN-002` | `primary_pattern` NULL 시도 | FATAL — **이 브랜치에서 `anomaly_results` 미적재이나 핸들러 등록 필요** |
| `DB-ARR-001` | `pattern_types` 빈 배열 `{}` 적재 | FATAL — **이 브랜치에서 `anomaly_results` 미적재이나 핸들러 등록 필요** |
| `DB-ARR-002` | `bp_dates` 파싱 실패 (형식 불일치) | WARN — `NULL`로 적재 (D-07) |
| `DB-RUN-001` | 동일 `run_date`로 `pipeline_runs` 중복 생성 | FATAL — 수동 개입 필요 |
| `PARSE-DATE-001` | `DATE` → `YYYY-MM` 변환 실패 (DB→API Pydantic 경계) | CLIENT_500 — **이 브랜치는 API 엔드포인트 미구현이나 공통 예외 핸들러 등록 필요** (`feat/be-api-*` 실제 발생 경계) |
| `PARSE-ARR-001` | `VARCHAR[]` → Python list 변환 실패 | CLIENT_500 — **이 브랜치는 API 엔드포인트 미구현이나 공통 예외 핸들러 등록 필요** |
| `PARSE-ENUM-001` | DB 열거형 값이 Pydantic `Literal` / `Enum` 범위 밖 | CLIENT_500 — **이 브랜치는 API 엔드포인트 미구현이나 공통 예외 핸들러 등록 필요** |

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간), `banana` (4구간) — Phase 2~3 출력 CSV 존재 확인 후 사용 |
| 테스트 Phase | Phase 2~3 우선 (S3 착수 시점 Phase 4~6 미완료 시 — Phase 2~3만 적재 후 완료 기준 충족 가능) |
| 특수 케이스 | Phase 5 (4구간 품목 구간 C만 존재) / Phase 6 `bp_dates` 파싱 실패 → `DB-ARR-002` WARN 확인 / `period.day != 1` 의도적 주입 → `DB-TYPE-001` FATAL 확인 |
| 테스트 픽스처 위치 | Phase 2·3: `tests/fixtures/pipeline/phase2_sample.csv`, `tests/fixtures/pipeline/phase3_sample.csv` / Phase 4~6 (파일 존재 시): `tests/fixtures/pipeline/phase4_{cid}_{seg}_model.json`, `tests/fixtures/pipeline/phase4_{cid}_{seg}_irf.csv`, `tests/fixtures/pipeline/phase4_{cid}_{seg}_baseline.json`, `tests/fixtures/pipeline/phase5_granger_results.csv`, `tests/fixtures/pipeline/phase6_{cid}_{seg}_breakpoints.json` |
| 더미 → 실제 전환 트리거 | Phase 2~3 CSV 파일이 `data/processed/` 경로에 실제 존재할 때 실 적재 실행 |

---

## 7. 완료 기준

> 주관적 판단이 개입되지 않도록 수치·상태로 기술한다.

| 항목 | 기준 |
|------|------|
| Migration 적용 | `alembic upgrade head` — revision 0003·0004·0005 오류 없이 적용 확인. `stationarity_results`, `cointegration_results`, `model_params`, `irf_data`, `baselines`, `granger_results`, `breakpoints`, `subperiods` 8개 테이블 생성 확인 |
| Phase 2~3 적재 | `wheat`, `banana` 샘플 품목 기준 `stationarity_results`, `cointegration_results` 실제 DB 적재 확인 (행 수 > 0) |
| `pipeline_runs` 기록 | 적재 성공 시 `status='completed'` 1건 이상 정상 기록 확인 |
| 트랜잭션 롤백 | 의도적 실패(Phase 3 적재 중 FK 오류 주입) → `DB-TX-001` FATAL, Phase 3 전체 롤백, `pipeline_runs.status='failed'` 기록 확인 |
| `period` 검증 | `period = '2026-03-15'` (월초 아님) 주입 시 `DB-TYPE-001` FATAL 발생 확인 |
| ORM 모델 | `db_schema_vN.md §Phase 2~6 테이블` ↔ `app/db/models/phase2_3.py`·`phase4_5.py`·`phase6.py` ORM 모델 컬럼명·타입 불일치 0건 |
| 예외 코드 | §5.1 예외 코드 전체 핸들러 등록 확인 (FATAL·WARN·UPSERT 각 처리 방침 동작 확인) |
| 파라미터 | §4 파라미터 3종 전체 `settings.py` 참조 확인, 하드코딩 0건 |
| `autogenerate` 미사용 | Alembic revision 3개 모두 수동 작성 확인 (`frame_spec §8.9`) |
| `data_freshness` 갱신 | Phase 전체 완료 후 `data_freshness.data_up_to`·`next_run_date` UPSERT 확인 (1행 유지) |
| 결과 명세 | `docs/results/DB-PIPELINE.md` 작성 완료 (적재 행 수, 테이블별 샘플 데이터 캡처 포함) |
| 후속 선행 조건 | `feat/be-api-timeseries`, `feat/be-api-panel`, `feat/be-redis` 착수 가능 상태 |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| Alembic `autogenerate` 사용 | `frame_spec_backend_vN §8.9` 위반 — Frame 정의 외 테이블 누락 위험 |
| §4 파라미터 값 코드 하드코딩 (`PIPELINE_DATA_ROOT="data/processed"` 등) | `settings.py` 단일 관리 원칙 위반 |
| `exception_spec_vN` 미등록 예외 코드 임의 생성 | `exception_spec §사용 규칙` 위반. 신규 상황은 `(proposed)` 표식 후 PM 리뷰 필수 |
| Phase 롤백 없이 다음 Phase 진행 | `db_schema_vN §설계 원칙 7 (D-17)` 위반 — 데이터 정합성 파괴 |
| `period.day != 1` 행 DB 적재 | `db_schema_vN §설계 원칙 6 (D-11)` 위반 — 반드시 `DB-TYPE-001` FATAL 처리 |
| `anomaly_results`에 `confidence_grade IS NULL` 행 적재 | `db_schema_vN §설계 원칙 5 (D-02)` 위반 — 이 브랜치는 `anomaly_results` 미적재이나, `feat/phase7` 구현 시 반드시 적용해야 하는 원칙으로 핸들러 등록 필요 |
| `bp_dates` 파싱 실패 시 FATAL 처리 | `exception_spec_vN §DB-ARR-002`는 WARN — NULL 적재 후 계속 진행 (D-07) |
| Phase 7·7-ML·8 테이블 migration 이 브랜치에서 작성 | 해당 feat 브랜치 담당 범위 (`feat/phase7-*`) |
| 이 브랜치에서 API 엔드포인트 구현 | 적재 스크립트 레이어만 담당. API는 `feat/be-api-*` 브랜치 담당 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| Alembic revision 3개가 `db_schema_vN §Phase 2~6 테이블`과 정합한가 | ☐ |
| ORM 모델 파일을 `frame_spec §8.6` 분할 기준(`phase2_3.py`, `phase4_5.py`, `phase6.py`)으로 작성하는 것을 승인하는가 (단일 `pipeline.py` 통합 vs 분할 최종 결정 필요) | ☐ |
| `pipeline_runs` 기록 규칙이 `feat/be-batch`와 충돌 없는가 | ☐ |
| Phase 4 `subperiod_id IS NULL` 우선 적재 → Phase 6 완료 후 하위 기간 보정 방식을 승인하는가 | ☐ |
| §4 `PIPELINE_DATA_ROOT` 키를 `frame_spec_backend_vN §4` 미등록 신규 키로 `settings.py`에 추가하는 것을 승인하는가 (`frame_spec §4` 갱신 연동 필요) | ☐ |
| §4 `DB_POOL_SIZE` 키도 `frame_spec_backend_vN §4` 미등록 신규 키 — `frame_spec §5 pool_size=10`과 중복 관리 리스크 인지 후 승인하는가 | ☐ |
| §5.1 예외 코드 전체가 `exception_spec_vN §8 기능별 매핑` 표와 일치하는가 | ☐ |
| 테스트 품목 `wheat`, `banana` Phase 2~3 CSV 파일이 제공 가능한가 | ☐ |

**승인일**: ____________________  
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `feat/be-db-pipeline` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-db-pipeline
- **기능 번호**: DB-PIPELINE
- **Feature 명세**: docs/feature_spec_DB-PIPELINE_v2.md
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] Migration 적용: alembic upgrade head 오류 없음, 8개 테이블 생성 확인
- [ ] Phase 2~3 적재: wheat·banana 샘플 품목 DB 적재 확인 (행 수 > 0)
- [ ] pipeline_runs 기록: status='completed' 1건 이상 확인
- [ ] data_freshness UPSERT: Phase 완료 후 data_up_to·next_run_date 갱신 확인
- [ ] 트랜잭션 롤백: 의도적 실패 → DB-TX-001 + pipeline_runs.status='failed' 확인
- [ ] period 검증: DB-TYPE-001 FATAL 발생 확인
- [ ] ORM 모델 컬럼명·타입 불일치 0건 (phase2_3.py, phase4_5.py, phase6.py)
- [ ] 파라미터 settings.py 참조 확인 (하드코딩 0건)
- [ ] autogenerate 미사용 확인 (3개 revision 수동 작성)
- [ ] 결과 명세 docs/results/DB-PIPELINE.md 작성

## 필드명 일치 확인
- [ ] db_schema_vN.md ↔ pipeline_output_spec_vN.md ↔ app/db/models/phase2_3.py·phase4_5.py·phase6.py 컬럼명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: DB-CONN-001~002, DB-TX-001, DB-UNIQ-001~003, DB-FK-001~003, DB-TYPE-001~002, DB-NN-001~002, DB-ARR-001~002, DB-RUN-001, PARSE-DATE-001, PARSE-ARR-001, PARSE-ENUM-001
- 신규 제안 코드: {없음 / (proposed) 표식 포함 목록}

## 로컬 실행 증빙
{alembic upgrade head 로그·적재 결과 행 수·pipeline_runs 캡처 붙여넣기}

## 리뷰어 확인 요청 사항
- Phase 4 subperiod_id IS NULL 우선 적재 방식 최종 확인 요청
- Phase 6 완료 후 하위 기간 보정 배치 일정 협의 필요

## 기타
- Phase 7·7-ML·8 테이블 migration은 feat/phase7-* 담당
- Redis 캐시 무효화 트리거는 feat/be-redis 담당
```
