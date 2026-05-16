# 결과 명세 — BE-BATCH

**기능 번호**: BE-BATCH  
**브랜치**: `feat/be-batch`  
**Feature 명세**: `docs/feature_specs/feature_spec_BE-BATCH_v2.md`  
**담당자**: 바게스타니 샤킬라  
**작성일**: 2026-05-16  
**상태**: 구현 완료 (더미 모드) / 실 파이프라인 연동 대기 (`feat/be-db-pipeline` dev 머지 후)

---

## 구현 완료 항목 (feature_spec_BE-BATCH_v2 §7 완료 기준)

| 항목 | 상태 | 비고 |
|------|------|------|
| APScheduler cron 등록 (매월 15일 03:00 KST) | ✅ | `app/services/batch.py` `init_scheduler()` |
| `run_monthly_pipeline()` Phase 0~7-ML 순차 호출 | ✅ (더미) | `_run_phase()` 스텁 — feat/be-db-pipeline 연동 시 교체 |
| `pipeline_runs` UPSERT (status, phases_run, error_message) | ✅ | `ON CONFLICT (run_date) DO UPDATE` |
| `data_freshness` 갱신 (completed 시에만) | ✅ | UPDATE → 0건이면 INSERT |
| 배치 실패 시 ERROR 구조화 로그 (API-BATCH-001) | ✅ | `error_code`, `context.run_date`, `context.stage` 포함 |
| 수동 트리거 `POST /api/v1/admin/batch/trigger` | ✅ | 202 Accepted, 비동기 실행 |
| 중복 실행 방지 (API-BATCH-002) | ✅ | `status='running'` + 동일 `run_date` 체크 |
| §4 파라미터 전체 settings 참조 | ✅ | 하드코딩 0건 |
| 더미 픽스처 `tests/fixtures/batch_pipeline_mock.py` | ✅ | `mock_batch_phases`, `mock_batch_phases_fail_at_phase7` |
| APScheduler lifespan 시작·종료 훅 | ✅ | `app/main.py` lifespan |

---

## 변경 파일 목록

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `app/services/batch.py` | **신규** | APScheduler 등록 + 배치 실행 로직 전체 |
| `app/core/config.py` | 수정 | `BATCH_SCHEDULE_DAY`, `BATCH_SCHEDULE_HOUR`, `BATCH_SCHEDULE_TZ`, `BATCH_MISFIRE_GRACE_SEC` 추가 |
| `app/main.py` | 수정 | lifespan에 `init_scheduler()` 시작·종료 훅 등록 |
| `app/schemas/meta.py` | 수정 | `BatchTriggerResponse` 스키마 추가 |
| `app/api/v1/endpoints/meta.py` | 수정 | `POST /admin/batch/trigger` 엔드포인트 추가 |
| `tests/fixtures/batch_pipeline_mock.py` | **신규** | 더미 Phase 픽스처 |
| `docs/results/BE-BATCH.md` | **신규** | 본 문서 |

---

## 필드명 3방향 일치 확인

| `db_schema_v5.md §pipeline_runs` | `app/db/models/batch.py` | `app/schemas/meta.py BatchTriggerResponse` |
|---|---|---|
| `id` | `id` | `run_id` (응답 필드) |
| `run_date` | `run_date` | `run_date` |
| `status` | `status` | `status` |
| `started_at` | `started_at` | `started_at` |

- 불일치 항목: `pipeline_runs.id` → 응답에서 `run_id`로 노출 (api_spec_vN 미반영 — 머지 후 PM에 반영 요청 필요, feature_spec_BE-BATCH_v2 §3.2 비고)

---

## 예외처리 구현 범위

| 코드 | 구현 위치 | 처리 방식 |
|------|-----------|-----------|
| `API-BATCH-001` | `batch.py` `_execute_phases()` | WARN + `status='failed'` 기록. 서버 유지. |
| `API-BATCH-002` | `batch.py` `_prepare_run()` | WARN + 실행 skip. 기존 run_id 반환. |
| `DB-RUN-001` | UPSERT 구조로 방지 | `ON CONFLICT DO UPDATE`로 중복 INSERT 차단. |
| `DB-TX-001` | `_execute_phases()` Phase 루프 | Phase 실패 시 raise → `API-BATCH-001`로 체이닝. |

---

## 파라미터 settings 참조 확인

```
BATCH_SCHEDULE_DAY   = settings.batch_schedule_day   (기본: 15)
BATCH_SCHEDULE_HOUR  = settings.batch_schedule_hour  (기본: 3)
BATCH_SCHEDULE_TZ    = settings.batch_schedule_tz    (기본: "Asia/Seoul")
BATCH_MISFIRE_GRACE_SEC = settings.batch_misfire_grace_sec (기본: 3600)
```

하드코딩 0건 확인.

---

## 로컬 실행 증빙

> 실제 DB 연결 후 수동 트리거 실행 로그·pipeline_runs 테이블 스크린샷은 `feat/be-db-pipeline` 머지 및 `APP_ENV=production` 전환 후 추가 예정.

### 더미 모드 실행 절차

```bash
# 1. 서버 기동
uvicorn app.main:app --reload --port 8000

# 2. 수동 트리거 (202 Accepted 확인)
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger

# 예상 응답:
# {
#   "run_id": 1,
#   "status": "running",
#   "run_date": "2026-05-16",
#   "started_at": "2026-05-16T..."
# }

# 3. 중복 실행 방지 (두 번째 호출 → API-BATCH-002 로그 확인)
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger
```

---

## 후속 선행 조건 (feat/be-redis 착수 조건)

- `pipeline_runs.id` 기반 캐시 무효화 트리거 연동 가능 상태: ✅
- `feat/be-redis` 착수 시 `pipeline_runs.id`를 Redis 캐시 키에 포함하여 갱신 여부 판단 (db_schema_v5 §D-18).

---

## 미완료 / 후속 작업

| 항목 | 사유 | 담당 |
|------|------|------|
| Phase 0~7-ML 실제 파이프라인 호출 | `feat/be-db-pipeline` 완료 대기 | 하대수 |
| `POST /admin/batch/trigger` api_spec_vN 반영 | 수동 트리거 엔드포인트 명세 미반영 | PM 최수안 |
| Redis 캐시 무효화 연동 | `feat/be-redis` 브랜치에서 처리 | 바게스타니 샤킬라 |
