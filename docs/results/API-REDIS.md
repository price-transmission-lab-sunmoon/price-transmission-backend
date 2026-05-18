# 구현 결과 명세 — API-REDIS (Redis 캐싱 적용)

**기능 번호**: `API-REDIS`
**브랜치**: `feat/be-redis`
**담당자**: 바게스타니 샤킬라
**작성일**: 2026-05-17
**근거 명세**: `docs/feature_specs/feature_spec_BE-REDIS_v2.md`

---

## 1. 구현 완료 항목 (feature_spec_BE-REDIS_v2 §7 완료 기준)

| 항목 | 상태 | 비고 |
|------|------|------|
| TTL 캐싱: `/stream`, `/raw-prices`, `/stat-series` | ✅ | 2회차 Redis HIT 로그 `cache=hit` 확인 가능 |
| ETag: 정적 엔드포인트 4종 304 응답 | ✅ | `/meta/pipeline`, `/meta/analysis-params`, `/segments`, `/events` |
| 캐시 무효화: 배치 완료 후 시계열 캐시 전체 삭제 | ✅ | `invalidate_cache(run_id)` 연결 완료 |
| DB-CACHE-001 폴백 구현 | ✅ | Redis 연결 실패 시 WARN + DB 직접 조회 |
| DB-CACHE-002 복구 구현 | ✅ | JSON 역직렬화 실패 시 키 삭제 + DB 재조회 |
| PARSE-REDIS-001 복구 구현 | ✅ | Pydantic 검증 실패 시 캐시 삭제 + DB 재조회 |
| 파라미터 `app/core/config.py` 참조 (하드코딩 0건) | ✅ | `REDIS_TTL`, `REDIS_CACHE_PREFIX`, `REDIS_URL` |
| `pytest tests/test_redis_cache.py` 오류 0건 | ✅ | 10개 단위 테스트 작성 |

---

## 2. 변경 파일 목록

| 구분 | 파일 | 변경 내용 |
|------|------|-----------|
| 수정 | `app/core/config.py` | `REDIS_TTL: int = 3600`, `REDIS_CACHE_PREFIX: str = "pricelens"` 신규 추가 |
| 수정 | `app/cache/redis.py` | `cache_get`, `cache_set`, `cache_delete`, `cache_delete_pattern` 헬퍼 추가 |
| 수정 | `app/api/v1/endpoints/commodities.py` | `/stream`, `/raw-prices` Redis 캐시 레이어 삽입 (Redis 의존성 주입 추가) |
| 수정 | `app/api/v1/endpoints/anomalies.py` | `/stat-series` Redis 캐시 레이어 삽입, `from_`/`to`/`granularity` 파라미터 추가 |
| 수정 | `app/api/v1/endpoints/meta.py` | 4개 정적 엔드포인트에 `If-None-Match` 비교 및 304 반환 로직 추가 |
| 수정 | `app/services/batch.py` | `invalidate_cache(pipeline_run_id)` 함수 신규 추가 + `_execute_phases` 완료 후 호출 |
| 신규 | `tests/test_redis_cache.py` | HIT/MISS/예외처리/무효화 단위 테스트 10개 작성 |
| 신규 | `docs/results/API-REDIS.md` | 본 결과 명세 |

---

## 3. 환경 변수 (app/core/config.py)

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `REDIS_URL` | (필수, 기존) | Redis 연결 문자열 |
| `REDIS_TTL` | `3600` | 캐시 TTL(초). PM 확정 전 기본값 사용 (`api_spec_vN §미결 사항`) |
| `REDIS_CACHE_PREFIX` | `"pricelens"` | 캐시 키 프리픽스 (개발/운영 환경 격리) |

---

## 4. 캐시 키 패턴 (feature_spec_BE-REDIS_v2 §3.3)

| 엔드포인트 | 캐시 키 패턴 |
|------------|-------------|
| `GET /api/v1/commodities/{commodity_id}/stream` | `pricelens:stream:{commodity_id}:{seg_key}:{from}:{to}:{granularity}` |
| `GET /api/v1/commodities/{commodity_id}/raw-prices` | `pricelens:raw-prices:{commodity_id}:all:{from}:{to}:{granularity}:{layout}` |
| `GET /api/v1/anomalies/{anomaly_id}/stat-series` | `pricelens:stat-series:{anomaly_id}:{metric}:{from}:{to}:{granularity}` |

> `from`/`to` 미지정 시 `"default"` 리터럴 사용. `REDIS_CACHE_PREFIX` 환경 변수 변경 시 패턴도 자동 반영.

---

## 5. ETag 처리 (정적 엔드포인트)

| 엔드포인트 | ETag 출처 | If-None-Match 처리 |
|------------|----------|-------------------|
| `GET /segments` | `ref_svc.get_segments()` 반환값 | 일치 시 304 반환 |
| `GET /events` | `ref_svc.get_events()` 반환값 | 일치 시 304 반환 |
| `GET /meta/pipeline` | 응답 body JSON SHA-256 앞 16자 | 일치 시 304 반환 |
| `GET /meta/analysis-params` | 응답 body JSON SHA-256 앞 16자 | 일치 시 304 반환 |

---

## 6. 예외처리 구현 요약

| 예외 코드 | 발생 레이어 | 처리 |
|-----------|------------|------|
| `DB-CACHE-001` | `cache_get`, `cache_set`, `cache_delete_pattern` | WARN 로그 + None/0 반환. 서비스 중단 없음. |
| `DB-CACHE-002` | `cache_get` 내 `json.loads()` 실패 | WARN 로그 + 해당 키 `delete` + None 반환 |
| `PARSE-REDIS-001` | `commodities.py`, `anomalies.py` Pydantic `model_validate` 실패 | WARN 로그 + `cache_delete` + DB 재조회 |

---

## 7. 캐시 무효화 흐름

```
pipeline_runs.status = 'completed'
  → _execute_phases() 완료 직후
  → invalidate_cache(pipeline_run_id)
    → cache_delete_pattern(client, "pricelens:stream:*")     → 삭제 N건 로그
    → cache_delete_pattern(client, "pricelens:raw-prices:*") → 삭제 N건 로그
    → cache_delete_pattern(client, "pricelens:stat-series:*") → 삭제 N건 로그
  → 다음 조회부터 DB 재조회 + 캐시 재적재
```

---

## 8. 미결 사항 (api_spec_vN §미결 사항 연동)

| 항목 | 현재 상태 | 확정 시점 |
|------|----------|---------|
| `REDIS_TTL` 확정값 | 기본값 `3600`초로 운영 | S6 백엔드 개발 착수 후 PM 확정 |
| 캐시 키 세부 규칙 | §4 패턴으로 운영 | S6 PM 확정 |
| minimap 캐시 무효화 | 미구현 (1차 출시 범위 외) | minimap 캐시 무효화 명세 확정 후 |

---

## 9. 후속 선행 조건

- `feat/fe-api-connect` dev 머지 전: Redis TTL 캐싱·304 응답·캐시 무효화 동작 확인 가능 상태 ✅
- `feat/be-batch`의 `app/services/batch.py`에서 `invalidate_cache(pipeline_run_id)` 인터페이스 변경 금지

---

*feature_spec_BE-REDIS_v2 §7 완료 기준 기준 작성. 로컬 실행 증빙은 PR 본문 참조.*
