# DB-PIPELINE 구현 결과 — feat/be-db-pipeline

**feature_spec_DB-PIPELINE_v2 §7 완료 기준 대조표**

| 기준 | 파일 | 상태 |
|------|------|------|
| Migration 적용 — 8개 테이블 생성 | alembic/versions/0005~0007_*.py | 완료 |
| stationarity_results 마이그레이션 | alembic/versions/0005_phase2_tables.py | 완료 |
| breakpoints/subperiods 마이그레이션 | alembic/versions/0006_phase6_tables.py | 완료 |
| model_params/irf_data/granger_results 마이그레이션 | alembic/versions/0007_phase4_5_tables.py | 완료 |
| ORM 모델 컬럼명·타입 불일치 0건 | app/db/models/phase2_3.py, phase4_5.py, phase6.py | 완료 |
| pipeline_runs 기록 유틸리티 | app/db/loader/base.py | 완료 |
| Phase 2 적재 스크립트 | app/db/loader/phase2.py | 완료 |
| Phase 3 적재 스크립트 | app/db/loader/phase3.py | 완료 |
| Phase 4 적재 스크립트 | app/db/loader/phase4.py | 완료 |
| Phase 5 적재 스크립트 | app/db/loader/phase5.py | 완료 |
| Phase 6 적재 스크립트 | app/db/loader/phase6.py | 완료 |
| runner.py — Phase 2→6 순차 실행 | app/db/loader/runner.py | 완료 |
| settings.py PIPELINE_DATA_ROOT, DB_POOL_SIZE 추가 | app/core/config.py | 완료 |
| autogenerate 미사용 확인 (3개 revision 수동 작성) | alembic/versions/0005~0007_*.py | 완료 |
| data_freshness UPSERT | app/db/loader/base.py:upsert_data_freshness | 완료 |
| 트랜잭션 롤백 (DB-TX-001) | 각 loader Phase 함수 | 완료 |
| period 검증 (DB-TYPE-001) | app/db/loader/base.py:validate_period_day | 완료 |
| bp_dates 파싱 실패 WARN (DB-ARR-002) | app/db/loader/phase6.py:_parse_bp_dates | 완료 |
| 파라미터 settings.py 참조 (하드코딩 0건) | 전 loader 파일 | 완료 |
| 테스트 픽스처 | tests/fixtures/pipeline/*.csv, *.json | 완료 |
| 단위/통합 테스트 | tests/test_db_pipeline.py | 완료 |
| 결과 명세 | docs/results/DB-PIPELINE.md | 완료 |

---

## 마이그레이션 체인

```
0001_initial_frame_tables
└─ 0002_seed_reference_data
   └─ 0003_add_baselines            ← baselines (feat/be-api-reference)
      └─ 0004_add_cointegration_results ← cointegration_results (feat/be-api-reference)
         └─ 0005_phase2_tables      ← stationarity_results (신규)
            └─ 0006_phase6_tables   ← breakpoints, subperiods (신규, FK 의존성 선행)
               └─ 0007_phase4_5_tables ← model_params, irf_data, granger_results
                                       + baselines·cointegration_results FK 추가
```

> **FK 순서 근거**: `model_params` / `irf_data` / `baselines` 모두 `subperiods.id` FK를 가지므로
> Phase 6 테이블(0006)을 Phase 4~5 테이블(0007)보다 먼저 생성.

---

## 주요 설계 결정

### NULL subperiod_id UPSERT 처리

`model_params`, `irf_data`, `baselines` 테이블은 `subperiod_id` 컬럼이 NULLABLE이며
전체 기간 행에서 NULL이다. PostgreSQL의 UNIQUE 제약은 NULL을 서로 다른 값으로 취급하므로
`ON CONFLICT (commodity_id, segment_id, subperiod_id) DO UPDATE` 구문이 동작하지 않는다.

**해결 방법**: Phase 4 트랜잭션 내에서 `DELETE WHERE subperiod_id IS NULL` 후 `INSERT` 수행.
멱등성 보장, Phase 4 단일 트랜잭션 범위 유지.

### Phase 6 → Phase 4 FK 의존성

Phase 6 테이블 마이그레이션(0006)을 Phase 4~5(0007)보다 선행:
- `model_params.subperiod_id` → `subperiods.id`
- `irf_data.subperiod_id` → `subperiods.id`
- `baselines.subperiod_id` → `subperiods.id` (0007에서 FK 추가)

### Phase 4 적재 순서 (runner)

Phase 2 → 3 → 4 → 5 → 6 순서로 실행:
- Phase 4 시점: `subperiods` 테이블이 비어 있으므로 `subperiod_id=NULL` 전체 기간 행만 적재
- Phase 6 완료 후: 하위 기간 모형 재실행 시 `subperiod_id` 값을 채워 추가 적재 (Phase 6 후보정, 별도 브랜치)

### granger_direction NULL 초기화

Phase 3에서 `cointegration_results.granger_direction=NULL`로 적재.
Phase 5에서 UPDATE로 4구간 품목 구간 C에만 `confirmed_direction` 값 갱신.

### bp_dates 파싱 실패 처리 (DB-ARR-002 WARN)

`bai_perron_breakpoints` 배열 항목 중 하나라도 `YYYY-MM` 파싱 실패 시:
- WARNING 로그 기록 (`DB-ARR-002`)
- `bp_dates = NULL` 적재 후 계속 진행 (FATAL 아님 — D-07)

---

## 예외 코드 커버리지

| 코드 | 처리 방침 | 구현 위치 |
|------|-----------|-----------|
| DB-TX-001 | Phase 전체 롤백 + 재발생 | 각 loader Phase 함수 |
| DB-TYPE-001 | FATAL — D-11 월초 검증 실패 | base.py:validate_period_day |
| DB-ARR-002 | WARN — bp_dates 파싱 실패 → NULL | phase6.py:_parse_bp_dates |
| DB-RUN-001 | FATAL — pipeline_runs 중복 run_date | base.py:create_pipeline_run |
| DB-CONN-001 | FATAL — PostgreSQL 연결 실패 | SQLAlchemy 예외 전파 |

---

## 테스트 픽스처 설명

| 파일 | 내용 |
|------|------|
| `tests/fixtures/pipeline/phase2_sample.csv` | wheat (3구간) + banana (4구간), 9행. banana wholesale_price 는 I(2) 케이스 포함 |
| `tests/fixtures/pipeline/phase3_sample.csv` | wheat 3구간 + banana 4구간 공적분 결과, 7행. banana segment C 는 I(2) 플래그 포함 |
| `tests/fixtures/pipeline/phase4_wheat_A_model.json` | wheat segment A VECM 파라미터 |
| `tests/fixtures/pipeline/phase4_wheat_A_irf.csv` | wheat segment A IRF 9행 (horizon 0~24) |
| `tests/fixtures/pipeline/phase4_wheat_A_baseline.json` | wheat segment A 기준선 |
| `tests/fixtures/pipeline/phase5_granger_results.csv` | banana segment C Granger 검정 2행 (양방향) |
| `tests/fixtures/pipeline/phase6_wheat_D_prime_breakpoints.json` | wheat D_prime 구조 변화 + 3개 하위 기간 |

---

## 테스트 케이스 목록 (tests/test_db_pipeline.py)

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_v_*` (5개) | `_v()` 헬퍼 — None, NaN, string, bool, 0 |
| `test_normalize_yyyymm_*` (3개) | 정상 변환, 유효하지 않은 월, 잘못된 형식 |
| `test_validate_period_day_*` (2개) | D-11 정상 통과, 월초 아님 → DB-TYPE-001 |
| `test_phase2_loads_csv` | 샘플 CSV → UPSERT 9회 호출, commit 확인 |
| `test_phase2_file_not_found` | 파일 없음 → DB-TX-001 |
| `test_phase2_rollback_on_db_error` | DB 오류 시 rollback + DB-TX-001 재발생 |
| `test_phase6_bp_dates_parse_ok` | YYYY-MM 배열 → DATE[] 변환 |
| `test_phase6_bp_dates_parse_warn_on_failure` | 파싱 실패 → None (WARN, FATAL 아님) |
| `test_phase6_bp_dates_empty` | 빈 배열 → [] |
| `test_period_day_not_1_is_fatal` | DB-TYPE-001 FATAL 발생 확인 |
| `test_runner_marks_failed_on_phase2_error` | Phase 2 실패 → status='failed', Phase 3 미실행 |
