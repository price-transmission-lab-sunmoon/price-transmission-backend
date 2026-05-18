# Feature 명세서 — Redis 캐싱 적용

**문서 유형**: Feature 명세서
**기능 번호**: `API-REDIS`
**브랜치명**: `feat/be-redis`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-05-09
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-05-09): 최초 작성.
- v2 (2026-05-11): 참조 문서 오류 수정. §0 exception_design_v3.md→exception_design_vN.md (vN 형식 통일). §1.2 캐시 무효화 패턴에 {REDIS_CACHE_PREFIX} 프리픽스 추가 (§3.3 키 정의와 일치). §1.2·§3.3 경로 파라미터 {id}→{commodity_id}/{anomaly_id} (pi_spec_v5 기준). §6 wheat (4구간)→(3구간), banana (3구간)→(4구간) (db_schema_v5 기준). PR 템플릿 파일명 eature_spec_API-REDIS_v1.md→eature_spec_BE-REDIS_v2.md.
- v2.1 (2026-05-18): §3.3 /stat-series 캐시 키 패턴에 {metric} 추가 (결과 명세 API-REDIS.md §4와 일치, metric별 데이터 상이).

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `api_spec_vN.md §설계 원칙 6, §미결 사항 캐시 키 규칙` | vN | 캐싱 대상 엔드포인트·ETag 정책·캐시 무효화 전략 | ☐ |
| `exception_spec_vN.md §Redis 캐시 (DB-CACHE-001, DB-CACHE-002), §PARSE-REDIS-001` | vN | Redis 예외 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md §Redis 복구 흐름` | v3 | Redis 연결 실패·역직렬화 실패 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2 디렉토리 구조, §4 환경 변수, §3 기술 스택` | vN | `app/cache/redis.py` 위치·Redis 클라이언트 초기화·`redis==5.0.4` 버전 확인. `REDIS_TTL`·`REDIS_CACHE_PREFIX`는 `frame_spec_backend_vN §4` 미등록 변수이므로 이 브랜치에서 `app/core/config.py`에 신규 추가 | ☐ |
| `db_schema_vN.md §pipeline_runs` | vN | `pipeline_runs.id` 기반 캐시 무효화 트리거 컬럼 확인 | ☐ |

> 백엔드(API-\*) 기능이므로 `pipeline_output_spec` 행 삭제.

---

## 1. 기능 개요

### 1.1 한 줄 요약

시계열 조회 엔드포인트(`/stream`, `/raw-prices`, `/stat-series`)에 Redis TTL 캐싱을 적용하고, `feat/be-api-reference`·`feat/be-api-meta`에서 이미 설정된 정적 엔드포인트 ETag 헤더를 기반으로 304 조건부 응답 처리를 추가하며, 배치 갱신 후 `pipeline_runs.id` 기반 캐시 자동 무효화를 구현한다.

### 1.2 데이터 흐름

```
[TTL 캐싱 경로 — 시계열 엔드포인트]
클라이언트 GET /api/v1/commodities/{commodity_id}/stream (+ /raw-prices, /stat-series)
  → app/api/v1/endpoints/commodities.py (또는 anomalies.py)
  → app/cache/redis.py: cache_get(cache_key)
    ├── HIT  → JSON 역직렬화 → Pydantic 검증 → 응답 반환
    └── MISS → SQLAlchemy DB 조회 → Pydantic 직렬화
              → app/cache/redis.py: cache_set(cache_key, value, ttl=REDIS_TTL)
              → 응답 반환

[캐시 무효화 경로 — 배치 완료 후]
배치 파이프라인 완료 → pipeline_runs.status = 'completed'
  → app/services/batch.py: invalidate_cache(pipeline_run_id)
  → app/cache/redis.py: cache_delete_pattern(f"{REDIS_CACHE_PREFIX}:stream:*", f"{REDIS_CACHE_PREFIX}:raw-prices:*", f"{REDIS_CACHE_PREFIX}:stat-series:*")
  → 다음 조회부터 DB 재조회 및 캐시 재적재

[ETag 경로 — 정적 엔드포인트]
클라이언트 GET /api/v1/meta/pipeline (또는 /meta/analysis-params, /segments, /events)
  → If-None-Match 헤더 포함 시 ETag 비교
    ├── 일치 → 304 Not Modified
    └── 불일치 → DB 조회 → 응답 + ETag 헤더 부착
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2` 디렉토리 구조 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/cache/redis.py` | 프레임에서 ping 전용으로만 생성된 파일에 `cache_get`, `cache_set`, `cache_delete_pattern` 헬퍼 함수 추가 |
| 수정 | `app/api/deps.py` | Redis 클라이언트 의존성 주입 함수 추가 (`get_redis`) |
| 수정 | `app/api/v1/endpoints/commodities.py` | `/stream`, `/raw-prices` 엔드포인트에 캐시 레이어 삽입 |
| 수정 | `app/api/v1/endpoints/anomalies.py` | `/stat-series` 엔드포인트에 캐시 레이어 삽입 |
| 수정 | `app/api/v1/endpoints/meta.py` | `/meta/pipeline`, `/meta/analysis-params`, `/segments`, `/events` — 기존 ETag 헤더 기반 `If-None-Match` 비교 로직 추가 및 304 응답 처리 |
| 수정 | `app/services/batch.py` | 배치 완료 후 캐시 무효화 트리거 로직 추가 |
| 수정 | `app/core/config.py` | `REDIS_TTL`, `REDIS_CACHE_PREFIX` 환경 변수 추가 |
| 신규 | `tests/test_redis_cache.py` | 캐시 HIT/MISS/무효화·예외처리 단위 테스트 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | `/stream`, `/raw-prices`, `/stat-series` Redis TTL 캐싱 (cache_get → DB 조회 → cache_set 흐름) |
| **구현** | `/meta/pipeline`, `/meta/analysis-params`, `/segments`, `/events` — `feat/be-api-reference`·`feat/be-api-meta`에서 설정된 ETag 헤더 기반 `If-None-Match` 비교 및 304 응답 처리 추가 (ETag 헤더 신규 설정은 비구현) |
| **구현** | 배치 완료 후 `pipeline_runs.id` 기반 시계열 캐시 전체 무효화 트리거 |
| **구현** | `DB-CACHE-001` (Redis 연결 실패 시 DB 직접 조회 폴백) |
| **구현** | `DB-CACHE-002` (JSON 역직렬화 실패 시 캐시 키 삭제 후 DB 재조회) |
| **구현** | `PARSE-REDIS-001` (API 레이어 Pydantic 검증 실패 시 캐시 무효화 후 DB 재조회) |
| **비구현** | Redis TTL 값 및 캐시 키 규칙 확정 — `api_spec_vN.md §미결 사항` 기준으로 S6 백엔드 개발 착수 후 PM이 확정. 확정값은 `app/core/config.py`에 반영하며, 확정 전 로컬 테스트는 기본값(`REDIS_TTL=3600`)으로 진행 |
| **비구현** | Redis Cluster / Sentinel 고가용성 구성 (1차 출시 범위 외) |
| **비구현** | 캐시 히트율 모니터링 대시보드 (1차 출시 범위 외) |
| **선행 조건** | `feat/be-db-pipeline` dev 머지 완료 (pipeline_runs 테이블 및 배치 완료 이벤트 존재) |
| **선행 조건** | `frame/backend` 커밋 기준 `app/cache/redis.py` ping 구현 완료 확인 |

---

## 2. 입력 데이터

> 이 기능은 캐싱 레이어로 DB를 직접 변경하지 않으나, 캐시 키 생성 및 무효화 트리거에 DB 컬럼을 참조한다.

| 출처 | 파일명 또는 테이블명 | 사용 컬럼 | 타입 | 비고 |
|------|---------------------|-----------|------|------|
| DB 테이블 | `pipeline_runs` | `id`, `status`, `run_date` | `INTEGER`, `VARCHAR`, `DATE` | 배치 완료 여부 확인 및 캐시 무효화 트리거 키로 사용 |
| HTTP 요청 | 시계열 엔드포인트 쿼리 파라미터 | `commodity_id`, `segment_id`, `from`, `to`, `granularity` | `str`, `str`, `str`, `str`, `str` | 캐시 키 구성 요소 |

> 정적 엔드포인트(`/meta/pipeline`, `/meta/analysis-params`, `/segments`, `/events`)의 ETag는 코드 내 정적 딕셔너리 기반이므로 별도 DB 조회 없음. `feat/be-api-reference`·`feat/be-api-meta`에서 이미 설정된 ETag 헤더값을 그대로 사용.

### 2.1 타입 변환 규칙

해당 없음. 이 기능은 캐싱 레이어로 DB ↔ API 간 타입 변환은 각 엔드포인트 기존 Pydantic 직렬화 로직에 위임한다.

---

## 3. 출력 데이터

### 3.1 파이프라인 출력 파일

해당 없음. (백엔드 캐싱 기능)

### 3.2 DB 적재 대상

해당 없음. 이 기능은 DB를 직접 쓰지 않는다. Redis는 인메모리 캐시로만 사용한다.

### 3.3 API 응답

| 엔드포인트 | 캐싱 방식 | 캐시 키 패턴 | 비고 |
|------------|-----------|-------------|------|
| `GET /api/v1/commodities/{commodity_id}/stream` | Redis TTL | `{REDIS_CACHE_PREFIX}:stream:{commodity_id}:{segment_id}:{from}:{to}:{granularity}` | MISS 시 DB 조회 후 캐시 적재 |
| `GET /api/v1/commodities/{commodity_id}/raw-prices` | Redis TTL | `{REDIS_CACHE_PREFIX}:raw-prices:{commodity_id}:{segment_id}:{from}:{to}:{granularity}:{layout}` | MISS 시 DB 조회 후 캐시 적재 |
| `GET /api/v1/anomalies/{anomaly_id}/stat-series` | Redis TTL | `{REDIS_CACHE_PREFIX}:stat-series:{anomaly_id}:{metric}:{from}:{to}:{granularity}` | MISS 시 DB 조회 후 캐시 적재 |
| `GET /api/v1/meta/pipeline` | ETag 조건부 | — | 코드 내 정적 딕셔너리 기반 ETag, 304 응답 |
| `GET /api/v1/meta/analysis-params` | ETag 조건부 | — | 동일 |
| `GET /api/v1/segments` | ETag 조건부 | — | 동일 |
| `GET /api/v1/events` | ETag 조건부 | — | 동일 |

> **미결**: Redis TTL 값(`REDIS_TTL`) 및 캐시 키 세부 규칙은 `api_spec_vN.md §미결 사항`에 따라 S6 백엔드 개발 착수 후 PM이 확정. 확정 전 로컬 테스트는 기본값 `3600`(초)으로 진행.

---

## 4. 파라미터 제약 조건

| 파라미터명 | `app/core/config.py` 키 | 기본값 | 하드코딩 금지 이유 | 비고 |
|------------|------------------------|--------|-------------------|------|
| Redis TTL (초) | `REDIS_TTL` | `3600` | 배치 주기·데이터 신선도 요건에 따라 조정 필요. PM 확정값 반영 예정 | 이 브랜치에서 신규 추가 (`frame_spec_backend_vN §4` 미등록) |
| Redis 캐시 키 프리픽스 | `REDIS_CACHE_PREFIX` | `"pricelens"` | 다중 환경(dev/prod) 격리 목적 | 이 브랜치에서 신규 추가 (`frame_spec_backend_vN §4` 미등록) |
| Redis URL | `REDIS_URL` | `"redis://localhost:6379/0"` | `frame_spec_backend_vN §4` 환경 변수 기준 | 프레임에서 이미 정의됨 |

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스 (반복 조회용)
> - **`exception_design_vN.md §Redis 복구 흐름`**: 에러 체이닝 구현 방식 (코드 구현용)

### 5.1 적용 예외 코드

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `DB-CACHE-001` | Redis 연결 자체 실패 (서버 다운, 네트워크 오류 등) | WARN — 캐시 없이 DB 직접 조회. 서비스 중단 없음. `redis_url_redacted`, `error_type` 로그 기록 |
| `DB-CACHE-002` | Redis에서 꺼낸 값의 JSON 역직렬화 실패 (배포 후 구 캐시와 신 스키마 불일치) | WARN — 해당 캐시 키 삭제 후 DB 재조회. `cache_key`, `raw_value_preview` 로그 기록 |
| `PARSE-REDIS-001` | API 레이어에서 Redis 캐시값 → Pydantic 검증 실패 | WARN — 캐시 무효화 후 DB 재조회. `DB-CACHE-002`와 감지 레이어만 다름 (이 코드는 API Pydantic 레이어에서 감지) |

### 5.2 신규 예외 코드 제안

해당 없음. 위 3종 모두 `exception_spec_vN.md`에 기등록된 코드다.

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 테스트 품목 | `wheat` (3구간), `banana` (4구간) |
| 테스트 기간 | 로컬 DB에 적재된 실제 기간 기준 (feat/be-db-pipeline 완료 이후) |
| 특수 케이스 | DB-CACHE-001: Redis 컨테이너 강제 종료 후 API 정상 응답 확인 / DB-CACHE-002: 캐시 스키마 변경 후 구 캐시 잔존 상태에서 조회 시 자동 무효화 확인 / 배치 완료 후 캐시 무효화: pipeline_runs.status='completed' 이후 캐시 재적재 확인 |
| 목업 파일 위치 | `tests/conftest.py` 내 Redis Mock fixture 정의 (`fakeredis` 또는 `unittest.mock.MagicMock` 활용) |
| 더미 → 실제 전환 트리거 | `feat/be-db-pipeline` dev 머지 완료 + 로컬 Redis 컨테이너 기동 후 |

---

## 7. 완료 기준

> 주관적 판단이 개입되지 않도록 수치·상태로 기술한다.

| 항목 | 기준 |
|------|------|
| TTL 캐싱 동작 | `/stream`, `/raw-prices`, `/stat-series` — 동일 파라미터 2회 연속 조회 시 2회차에서 Redis HIT 확인 (응답 로그 `cache=hit`) |
| ETag 동작 | `/meta/pipeline` 등 정적 엔드포인트 — `If-None-Match` 헤더 포함 재요청 시 304 응답 확인 |
| 캐시 무효화 | 배치 완료(`pipeline_runs.status='completed'`) 이후 시계열 캐시 전체 삭제 확인 (Redis `keys` 명령 기준 해당 패턴 0건) |
| DB-CACHE-001 폴백 | Redis 강제 종료 상태에서 `/stream` 조회 시 200 OK 반환 (서비스 중단 없음) 및 WARN 로그 확인 |
| DB-CACHE-002 복구 | 구 캐시 강제 주입 후 조회 시 해당 캐시 키 자동 삭제 후 DB 재조회 확인 |
| PARSE-REDIS-001 복구 | Pydantic 검증 실패 시 캐시 무효화 후 DB 재조회 확인 |
| 파라미터 | `REDIS_TTL`, `REDIS_CACHE_PREFIX`, `REDIS_URL` 전체 `app/core/config.py` 참조, 하드코딩 0건 |
| 목업 실행 | `pytest tests/test_redis_cache.py` 오류 0건 |
| 결과 명세 | `docs/results/API-REDIS.md` 작성 완료 |
| 후속 선행 조건 | `feat/fe-api-connect` dev 머지 전 Redis TTL 캐싱·304 응답·캐시 무효화 동작 확인 가능 상태 |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| `REDIS_TTL`, `REDIS_CACHE_PREFIX`, `REDIS_URL` 코드 하드코딩 | `app/core/config.py` 단일 관리 원칙 위반 |
| Redis 연결 실패 시 서비스 중단 (예외 미처리 후 500 반환) | `DB-CACHE-001` 방침 위반 — 반드시 DB 폴백 후 WARN 처리 |
| 캐시 키 충돌 방지를 위한 `REDIS_CACHE_PREFIX` 미적용 | 개발/운영 환경 간 캐시 혼용 위험 |
| `exception_spec_vN.md` 미등록 Redis 예외 코드 임의 생성 | `exception_spec_vN §사용 규칙` 위반. 신규 상황은 `(proposed)` 표식으로 제안 후 PM 확정 |
| Redis를 DB 대체 영구 저장소로 사용 | Redis는 인메모리 캐시 전용. 영구 데이터 저장은 PostgreSQL만 허용 |
| `frame_spec_backend_vN §3`에 명시된 `redis==5.0.4` 외 버전 사용 | 버전 재현성 파괴 |

---

## 9. Pull Request 템플릿

> `feat/be-redis` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-redis
- **기능 번호**: API-REDIS
- **Feature 명세**: `docs/feature_spec_BE-REDIS_v2.md`
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] TTL 캐싱: `/stream`, `/raw-prices`, `/stat-series` 2회차 Redis HIT 확인
- [ ] ETag: 정적 엔드포인트 4종 304 응답 확인
- [ ] 캐시 무효화: 배치 완료 후 시계열 캐시 전체 삭제 확인
- [ ] 예외처리 구현 (`DB-CACHE-001`, `DB-CACHE-002`, `PARSE-REDIS-001`)
- [ ] 파라미터 `app/core/config.py` 참조 확인 (하드코딩 0건)
- [ ] `pytest tests/test_redis_cache.py` 오류 0건
- [ ] 결과 명세 `docs/results/API-REDIS.md` 작성

## 필드명 3방향 일치 확인
- [ ] `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/` 필드명 일치 (캐시 키 구성 파라미터 기준)
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 구현한 예외 코드: `DB-CACHE-001`, `DB-CACHE-002`, `PARSE-REDIS-001`
- 신규 제안 코드: 없음

## 로컬 실행 증빙
- Redis HIT 로그 (동일 파라미터 2회 조회 응답 비교)
- Redis 강제 종료 후 `/stream` 200 OK 응답 로그
- 배치 완료 후 캐시 무효화 Redis keys 결과
- `pytest tests/test_redis_cache.py` 출력

## 리뷰어 확인 요청 사항
- 캐시 키 패턴 (`§3.3` 정의)이 향후 파라미터 확장 시에도 충돌 없는지 검토 요청
- `REDIS_TTL` 기본값 3600초 적절성 PM 최종 확인 요청 (api_spec_vN §미결 사항 연동)

## 기타
- `feat/be-batch`의 `app/services/batch.py`에 캐시 무효화 호출 지점이 연결되어 있으므로, feat/be-batch 착수 전 해당 인터페이스(`invalidate_cache(pipeline_run_id)`) 변경 금지
```
