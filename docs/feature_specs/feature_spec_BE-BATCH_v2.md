# Feature 명세서 — APScheduler 월별 자동 배치 + 파이프라인 결과 DB 적재

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: Feature 명세서
**기능 번호**: `BE-BATCH`
**브랜치명**: `feat/be-batch`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-05-07
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-05-07): 최초 작성. feat/be-batch 기능 명세 초안.
- v2 (2026-05-11): 오류 수정. 브랜치명 `feat/be-batch-APScheduler`→`feat/be-batch` (`exception_spec_v6 §8` 기준). §1.3 `app/core/config.py` 수정 항목에 `BATCH_MISFIRE_GRACE_SEC` 추가 (§4 파라미터 목록과 일치).

**작성 기준 문서** (최신 버전 자동 참조 — `abcd_vN.md` 규칙):
- `db_schema_vN.md`
- `api_spec_vN.md`
- `exception_spec_vN.md`
- `exception_design_vN.md`
- `frame_spec_backend_vN.md`
- `web_plan_vN.md`
- `feature_dev_list_vN.md`

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `pipeline_output_spec_vN.md §Phase 0~7-ML` | vN | 파이프라인 실행 결과 파일 경로·컬럼명·타입 확인 | ☐ |
| `db_schema_vN.md §pipeline_runs`, `§data_freshness` | vN | 배치 이력·갱신 시점 테이블 구조·UNIQUE 키 | ☐ |
| `api_spec_vN.md` | vN | 수동 트리거 엔드포인트 설계 기준 (§3.2). **현재 미반영 — 머지 후 PM에 api_spec 반영 요청 필요** | ☐ |
| `exception_spec_vN.md §API-BATCH`, `§DB-RUN` | vN | 배치 관련 에러 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md` | vN | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2`, `§8.7` | vN | 디렉토리 구조 확인 (`app/services/batch.py` 위치) | ☐ |
| `web_plan_vN.md §11.2` | vN | APScheduler 버전·배치 실행 시점 요건 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

APScheduler v3.10.4 기반으로 매월 15일 파이프라인(Phase 0~7-ML)을 자동 실행하고, 실행 결과를 `pipeline_runs` 및 `data_freshness` 테이블에 기록한다.

### 1.2 데이터 흐름

```
[APScheduler cron 트리거 — 매월 15일 03:00 KST]
  또는 [POST /api/v1/admin/batch/trigger — 개발용 수동 트리거]
      ↓
[app/services/batch.py — run_monthly_pipeline()]
  → Phase 0~7-ML 순차 실행 (각 Phase 스크립트 호출 — feat/pipeline-* 산출물)
  → pipeline_runs.status = 'running' → 'completed' | 'failed'
  → pipeline_runs.phases_run 갱신 (완료 Phase 목록 기록)
  → data_freshness 갱신 (data_up_to, next_run_date)
      ↓
[실패 시]
  → 하위 레이어(feat/be-db-pipeline) 예외 전파 수신
  → pipeline_runs.status = 'failed', error_message 기록
  → API-BATCH-001 WARN 로그 출력 (ERROR 레벨 구조화 로그, underlying_error 포함)
  → 서버 정상 유지, 다음 배치(익월 15일)까지 대기
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2 디렉토리 구조` 및 `§8.7 app/services/ 향후 분할 예고` 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 신규 | `app/services/batch.py` | APScheduler 스케줄 등록 + 배치 실행 로직 (§8.7 예고 파일) |
| 수정 | `app/main.py` | lifespan에 APScheduler 시작·종료 훅 등록 |
| 수정 | `app/api/v1/endpoints/meta.py` | 개발용 수동 트리거 엔드포인트 추가 (`POST /api/v1/admin/batch/trigger`) |
| 수정 | `app/core/config.py` | `BATCH_SCHEDULE_DAY`, `BATCH_SCHEDULE_HOUR`, `BATCH_SCHEDULE_TZ`, `BATCH_MISFIRE_GRACE_SEC` 환경 변수 추가 |
| 수정 | `app/db/models/batch.py` | `pipeline_runs`, `data_freshness` ORM 모델 — Frame에서 정의된 파일, 필요 시 컬럼 보완 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | APScheduler cron 스케줄 등록 (매월 15일 03:00 KST) |
| **구현** | `run_monthly_pipeline()` 함수 — Phase 0~7-ML 순차 호출 및 DB 적재 |
| **구현** | 배치 실행 결과 `pipeline_runs` UPSERT (status, phases_run, error_message) |
| **구현** | `data_freshness` 갱신 (data_up_to, next_run_date) |
| **구현** | 배치 실패 시 ERROR 레벨 구조화 로그 출력 (exception_spec_vN §API-BATCH-001 방침) |
| **구현** | 개발용 수동 트리거 엔드포인트 `POST /api/v1/admin/batch/trigger` |
| **구현** | 배치 중복 실행 방지 로직 (API-BATCH-002) |
| **비구현** | Redis 캐시 무효화 — `feat/be-redis` 브랜치에서 처리 |
| **비구현** | 배치 결과를 외부에 알림(이메일·슬랙 등) |
| **비구현** | Phase별 파이프라인 로직 자체 구현 — 각 `feat/pipeline-*` 브랜치 완료 산출물 호출만 |
| **선행 조건** | `frame/backend` dev 머지 완료 |
| **선행 조건** | `feat/be-api-reference` dev 머지 완료 (`feature_dev_list_vN` 기준) |

---

## 2. 입력 데이터

이 기능은 파이프라인 실행을 트리거하며, 파이프라인 각 Phase의 출력 파일을 DB에 적재한다.
배치 서비스 자체의 직접 입력은 아래와 같다.

| 출처 | 파일명 또는 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|---------------------|-----------|------|------|
| DB 테이블 | `pipeline_runs` | `run_date`, `status` | `DATE`, `VARCHAR(20)` | 중복 실행 여부 확인 (API-BATCH-002) |
| DB 테이블 | `data_freshness` | `data_up_to`, `next_run_date` | `DATE` | 현재 갱신 시점 조회 |
| 환경 변수 | `settings.py` | `BATCH_SCHEDULE_DAY`, `BATCH_SCHEDULE_HOUR`, `BATCH_SCHEDULE_TZ` | `int`, `int`, `str` | 스케줄 파라미터 |

### 2.1 타입 변환 규칙

| 변환 위치 | AS-IS | TO-BE | 규칙 |
|-----------|-------|-------|------|
| 배치 실행 시점 → DB 기록 | Python `datetime` (KST) | `TIMESTAMPTZ` | `started_at`, `finished_at` 컬럼에 UTC로 저장 |
| 데이터 기준 시점 → DB | 배치 실행월 기준 전월말 | `DATE (YYYY-MM-01)` | `period.day == 1` 검증 후 저장 (DB-TYPE-001 방지) |

---

## 3. 출력 데이터

> 이 기능은 파이프라인 출력 파일을 직접 생성하지 않으므로 §3.1(파이프라인 출력 파일) 섹션은 삭제한다.

### 3.1 DB 적재 대상

**적재 방식 정의**
- **UPSERT**: UNIQUE 키 충돌 시 갱신 (표준 경로)

| DB 테이블 | 적재 컬럼 | UNIQUE 키 | 필터 조건 | 적재 방식 | 트랜잭션 단위 |
|-----------|-----------|-----------|-----------|-----------|---------------|
| `pipeline_runs` | `run_date`, `data_up_to`, `next_run_date`, `status`, `phases_run`, `error_message`, `started_at`, `finished_at` | `(run_date)` | 항상 기록 | UPSERT | 배치 전체 단위 (Phase별 중간 갱신 포함) |
| `data_freshness` | `data_up_to`, `next_run_date`, `last_updated` | — (단일 행 관리) | 배치 status = 'completed' 시에만 갱신 | UPDATE | 배치 완료 시 단독 트랜잭션 |

> `pipeline_runs.phases_run`: 완료된 Phase를 순서대로 기록 (예: `{'0','1','2','3','4','5','6','7','7-ml'}`). Phase 실패 시 해당 Phase는 미기록.

### 3.2 API 응답

개발용 수동 트리거 엔드포인트의 응답.

| 엔드포인트 | 주 참조 테이블 | 응답 필드 | 비고 |
|------------|---------------|-----------|------|
| `POST /api/v1/admin/batch/trigger` | `pipeline_runs` | `run_id`, `status`, `run_date`, `started_at` | 배치 실행 시작 확인용. 비동기 실행 → 즉시 `202 Accepted` 반환 |

```json
// 202 Accepted 응답 예시
{
  "run_id": 1,
  "status": "running",
  "run_date": "2026-05-15",
  "started_at": "2026-05-15T18:00:00Z"
}
```

---

## 4. 파라미터 제약 조건

| 파라미터명 | `settings.py` 키 | 기본값 | 하드코딩 금지 이유 |
|------------|------------------|--------|-------------------|
| 배치 실행 일 (매월) | `BATCH_SCHEDULE_DAY` | `15` | 실행 일정 변경 시 코드 수정 없이 환경 변수로 조정 |
| 배치 실행 시각 (시, KST) | `BATCH_SCHEDULE_HOUR` | `3` | 서버 부하·데이터 수집 완료 시점에 따라 조정 가능 |
| 배치 타임존 | `BATCH_SCHEDULE_TZ` | `"Asia/Seoul"` | 서버 배포 리전 변경 시 유연하게 대응 |
| APScheduler misfire grace time (초) | `BATCH_MISFIRE_GRACE_SEC` | `3600` | 서버 재기동 후 유예 시간, 운영 정책 변경 가능 |

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스. 발생 조건·처리 방침 확인 시 참조한다. (반복 조회용)
> - **`exception_design_vN.md`**: 에러 체이닝 구현 설계. 실제 코드 작성 시 이 문서의 구현 패턴을 따른다. (코드 구현용)

### 5.1 적용 예외 코드

> `exception_spec_vN.md §8 기능별 예외처리 매핑` 기준. `feat/be-batch` 구현 필수 코드는 3개.

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `API-BATCH-001` | APScheduler 월별 배치 실행 중 예외 발생 | WARN. `pipeline_runs.status='failed'` 기록. 서버 유지. 다음 배치(익월 15일)까지 대기. |
| `API-BATCH-002` | 동일 `run_date`에 배치 중복 실행 감지 (락 확인 실패) | WARN. 실행 skip. 기존 실행 완료까지 대기. |
| `DB-RUN-001` | 동일 `run_date`로 `pipeline_runs` INSERT 시도 중복 발생 | FATAL. 수동 개입 요구. |

> **참조 — 하위 전파 코드** (`feat/be-db-pipeline`에서 구현, 이 브랜치에서 재구현 금지):
> `DB-TX-001` (Phase 트랜잭션 실패), `DB-CONN-001/002` (DB 연결 실패·pool 고갈), `DB-TYPE-001` (period 월초 검증 실패)
> 위 코드들은 파이프라인 실행 중 전파되어 `API-BATCH-001`의 `underlying_error`로 기록된다.

### 5.2 신규 예외 코드 제안

해당 없음. (기존 코드로 모든 시나리오 커버 가능)

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간), `banana` (4구간) — db_schema_vN §초기 데이터 기준 |
| 테스트 기간 | 수동 트리거로 즉시 실행 → 현재 시점 기준 1회 배치 완료 확인 |
| 특수 케이스 | (1) 배치 중 의도적 DB 연결 오류 유발 → `pipeline_runs.status='failed'` 기록 확인 / (2) 동일 `run_date`로 수동 트리거 2회 실행 → 두 번째 실행 skip 확인 (API-BATCH-002) |
| 목업 파일 위치 | `tests/fixtures/batch_pipeline_mock.py` — 실제 Phase 실행 대신 더미 함수로 대체하여 배치 흐름만 테스트 |
| 더미 → 실제 전환 트리거 | `feat/be-db-pipeline` dev 머지 완료 후, `APP_ENV=production` 전환 시 실제 파이프라인 호출 |

---

## 7. 완료 기준

> 주관적 판단이 개입되지 않도록 수치·상태로 기술한다.

| 항목 | 기준 |
|------|------|
| 기능 완성 | 수동 트리거(`POST /api/v1/admin/batch/trigger`) 실행 → Phase 0~7-ML 순차 호출 완료 |
| DB 적재 | `pipeline_runs` 1건 이상 정상 기록 (status = 'completed', phases_run 전체 기록) |
| DB 적재 | `data_freshness` 갱신 확인 (data_up_to, next_run_date 정상 값) |
| 예외처리 — 실패 시나리오 | 의도적 Phase 실패 유발 → `pipeline_runs.status='failed'`, error_message 기록 확인 |
| 예외처리 — 중복 실행 방지 | 동일 run_date 수동 트리거 2회 → 두 번째 skip, API-BATCH-002 WARN 로그 확인 |
| 로그 | 배치 실패 시 ERROR 레벨 JSON 구조화 로그 출력 확인 (`code`, `context.run_date`, `context.stage` 포함) |
| 파라미터 | §4 파라미터 전체 `settings.py` 참조 확인, 하드코딩 0건 |
| 목업 실행 | §6 기준 더미 모드 로컬 실행 오류 없음 |
| 결과 명세 | `docs/results/BE-BATCH.md` 작성 완료 (실행 로그·스크린샷 첨부) |
| 후속 선행 조건 | `feat/be-redis` 착수 가능 상태 (pipeline_runs.id 기반 캐시 무효화 트리거 연동 가능) |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| §4 파라미터 값 코드 하드코딩 (`15`, `3`, `"Asia/Seoul"` 등) | `settings.py` 단일 관리 원칙 위반 |
| APScheduler 스케줄 등록을 `app/main.py`에 직접 인라인 작성 | `app/services/batch.py` 단일 관리 원칙 위반 (frame_spec_backend_vN §8.7) |
| 배치 실패 시 서버 프로세스 종료 | API-BATCH-001 처리 방침 위반 — 서버는 항상 유지 |
| `exception_spec_vN.md` 미등록 예외 코드 임의 생성 | exception_spec_vN §10 규칙 위반 |
| Phase별 파이프라인 로직을 이 브랜치에서 새로 구현 | 각 `feat/pipeline-*` 브랜치 산출물 호출만 허용 |
| `pipeline_runs`에 동일 `run_date` INSERT (UPSERT 우회) | DB-RUN-001 유발, 이력 관리 파괴 |

---

## 9. Pull Request 템플릿

> `feat/be-batch` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-batch
- **기능 번호**: BE-BATCH
- **Feature 명세**: `docs/feature_spec_BE-BATCH_v2.md`
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] 기능 완성: 수동 트리거 → Phase 0~7-ML 순차 호출 완료
- [ ] DB 적재: `pipeline_runs` 정상 기록 (status='completed', phases_run 전체)
- [ ] DB 적재: `data_freshness` 갱신 확인
- [ ] 예외처리: 실패 시나리오 → status='failed', error_message 기록 확인
- [ ] 예외처리: 중복 실행 방지 → API-BATCH-002 WARN 로그 확인
- [ ] 로그: ERROR 레벨 JSON 구조화 로그 확인
- [ ] 파라미터 settings.py 참조 확인 (하드코딩 0건)
- [ ] 목업 실행 성공 (더미 모드)
- [ ] 결과 명세 `docs/results/BE-BATCH.md` 작성

## 필드명 3방향 일치 확인
- [ ] `db_schema_vN.md §pipeline_runs` ↔ `app/db/models/batch.py` ↔ `app/schemas/meta.py` 필드명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: `API-BATCH-001`, `API-BATCH-002`, `DB-RUN-001`
- 전파 수신 코드 (feat/be-db-pipeline 구현): `DB-TX-001`, `DB-CONN-001`, `DB-CONN-002`, `DB-TYPE-001`
- 신규 제안 코드: 없음

## 로컬 실행 증빙
{수동 트리거 실행 로그·pipeline_runs 테이블 스크린샷 붙여넣기}

## 리뷰어 확인 요청 사항
- APScheduler misfire_grace_time 기본값 3600초 적절성 검토
- 수동 트리거 엔드포인트(`/admin/batch/trigger`) api_spec_vN 반영 일정 협의
- data_freshness 단일 행 관리 방식 최종 승인

## 기타
- feat/be-redis 착수 시 pipeline_runs.id 기반 캐시 무효화 트리거 연동 필요
```

---

## PM 승인

| 항목 | 확인 |
|------|------|
| 선행 조건(`feat/be-api-reference` 완료) 명시 확인 | ☐ |
| §4 파라미터 전체 settings.py 키로 관리되는가 | ☐ |
| 배치 실패 시 서버 유지 방침이 exception_spec_vN과 일치하는가 | ☐ |
| 수동 트리거 엔드포인트가 개발용임이 명시되어 있는가 | ☐ |
| 완료 기준이 수치·상태 기반인가 (주관적 판단 없음) | ☐ |

**승인일**: YYYY-MM-DD
**승인자**: PM 최수안
