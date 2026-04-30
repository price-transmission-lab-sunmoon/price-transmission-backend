# 예외처리 설계 문서 (v2)

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: 예외처리 설계 — 에러 체이닝 구현 + 상관관계 매트릭스 + 설계 문제점 연결
**작성일**: 2026-04-28
**관련 문서**: 에러 코드 인덱스 및 처리 방침 → `exception_spec_v4.md`
**변경 이력**:
- v1 (2026-04-27): 최초 작성. exception_spec_v3 기준 에러 체이닝 설계·상관관계 매트릭스·설계 문제점 분리.
- v2 (2026-04-28): exception_spec_v4 반영. §2.3 출력 예시·§2.5 AI 전달 포맷을 백엔드·프론트 실제 코드 기반으로 교체. §3 상관관계 매트릭스를 PL-* 제거 후 DB→API→FE 전파 경로로 전면 재작성.

> **사용 목적**: 이 문서는 반복 조회용이 아니다. 에러 체이닝 구조 설계·구현, 에러 전파 경로 분석, 설계 미결 사항 추적 시 참조한다.

---

## 1. 설계 목적

에러 코드만으로는 전파 경로의 ORIGIN을 즉시 특정하기 어렵다. 본 설계는 두 가지를 추가한다.

1. **ORIGIN 자동 추출**: 예외 체인을 역추적하여 최초 발생 지점과 context 스냅샷을 한 줄로 출력 → AI와 사람 모두 ORIGIN 메서드 하나에 집중할 수 있다.
2. **상관관계 매트릭스**: 상류 에러가 하류에서 유발하는 연쇄를 정적으로 기술 → 로그에서 에러 코드만 봐도 역추적 경로를 알 수 있다.

---

## 2. 에러 체이닝 구현

### 2.1 핵심 원리

파이썬의 `__cause__` 속성을 이용해 예외 체인을 역추적한다.

- `raise X from Y` 시: `X.__cause__ = Y`
- 체인의 끝(`__cause__ is None`)이 **ORIGIN**
- ORIGIN의 `context`가 AI 진단의 주요 단서 — 이것이 체이닝 구조를 도입하는 핵심 이유

**컨벤션 전제 조건**: `raise X from e`를 반드시 지킨다. `from None` 또는 `from e` 생략 시 체인이 끊겨 ORIGIN 추적이 불가능해진다.

### 2.2 구현

```python
def trace_error_chain(exc: Exception) -> dict:
    """
    예외 체인을 역추적하여 ORIGIN과 전파 경로를 반환한다.

    Returns:
        {
            "origin": ProjectError,      # 최초 발생 예외
            "chain": [ProjectError, ...],# ORIGIN → 현재 순서
            "formatted": str             # AI·사람 전달용 포매팅 문자열
        }
    """
    chain = []
    current = exc

    while current is not None:
        chain.append(current)
        current = current.__cause__

    chain.reverse()  # ORIGIN이 첫 번째가 되도록
    origin = chain[0]

    return {
        "origin": origin,
        "chain": chain,
        "formatted": _format_chain(chain),
    }


def _format_chain(chain: list) -> str:
    lines = []

    for i, exc in enumerate(chain):
        if isinstance(exc, ProjectError):
            code = exc.code
            msg = exc.message
            snapshot_str = ""

            if i == 0 and exc.context:  # ORIGIN에만 context 출력
                items = ", ".join(
                    f"{k}={repr(v)}" for k, v in exc.context.items()
                )
                snapshot_str = f" | context: {{{items}}}"

            prefix = "ORIGIN" if i == 0 else "      "
            arrow = "  " if i == 0 else " └─ "
            lines.append(f"{prefix}{arrow}[{code}] {msg}{snapshot_str}")
        else:
            prefix = "ORIGIN" if i == 0 else "      "
            lines.append(f"{prefix}  [{type(exc).__name__}] {str(exc)}")

    return "\n".join(lines)
```

### 2.3 출력 예시

DB 연결 실패가 API 응답 실패로 전파되는 경우:

```
ORIGIN  [DB-CONN-002] SQLAlchemy async pool 고갈 | context: {pool_size=10, active=10, queue_wait_ms=5023}
        └─ [DB-CONN-001] PostgreSQL 연결 실패
              └─ [API-INT-001] 내부 예외 처리 실패
```

파싱 실패가 API 500으로 전파되는 경우:

```
ORIGIN  [PARSE-DATE-001] DB DATE → YYYY-MM 변환 실패 | context: {table='stat_timeseries', column='period', raw_value='0000-00-00'}
        └─ [API-INT-001] 내부 예외 처리 실패
```

### 2.4 전역 핸들러

```python
import traceback

def global_error_handler(exc: Exception):
    """
    최상위에서 잡힌 예외를 처리하는 핸들러.
    에러 체인을 분석하고 로그에 기록한다.
    """
    result = trace_error_chain(exc)

    print("=" * 60)
    print("[ 에러 발생 ]")
    print("=" * 60)
    print(result["formatted"])
    print("=" * 60)
    origin = result["origin"]
    origin_code = origin.code if isinstance(origin, ProjectError) else "UNKNOWN"
    print(f"ORIGIN 코드: {origin_code}")
    print("=" * 60)
```

**사용 위치**: 파이프라인 최상위 루프 또는 FastAPI 에러 미들웨어.

```python
try:
    run_main_logic()
except Exception as e:
    global_error_handler(e)
```

### 2.5 AI 디버깅 전달 포맷

에러 발생 시 AI에게 전달할 정보의 우선순위:

1. **ORIGIN 줄** (가장 중요): `[코드] 메시지 | context: {...}`
2. **CHAIN 목록**: 전파 경로 파악용
3. **ORIGIN 메서드 코드**: AI가 직접 읽을 수 있도록

```
# AI에게 전달하는 포맷 예시

ORIGIN  [DB-CONN-002] SQLAlchemy async pool 고갈 | context: {pool_size=10, active=10, queue_wait_ms=5023}
CHAIN:  DB-CONN-002 → DB-CONN-001 → API-INT-001
```

이 정보만 있으면 AI는 ORIGIN 메서드 하나만 집중 분석하여 원인을 진단할 수 있다.

---

## 3. 상관관계 매트릭스 (에러 전파)

상류 에러가 하류 단계에서 유발하는 연쇄 에러를 정리한다. 디버깅 시 본 매트릭스로 근본 원인을 역추적한다.

> **파이프라인(PL-*)은 예외처리 대상 외**이므로 매트릭스에서 제외. DB 레이어 이후부터 기술한다.

### DB 연결 실패 전파

```
DB-CONN-002  (pool 고갈, 재시도)
    └→ DB-CONN-001  (연결 실패 확정)
        └→ API-INT-001  (미들웨어 미매핑 → 500 반환)
            └→ FE-API-004  (프론트 500 수신 → FE_BLOCK)
```

### DB 적재 실패 전파

```
DB-UNIQ-002 / DB-UNIQ-003  (UNIQUE 위반)
    └→ UPSERT로 흡수 → 정상 진행

DB-FK-001 / DB-FK-002  (FK 참조 대상 없음)
    └→ DB-TX-001  (Phase 롤백)
        └→ API-BATCH-001  (배치 실패 기록)
            → pipeline_runs.status='failed'. 서버는 유지.

DB-NN-001  (confidence_grade NULL)
    └→ DB-TX-001  (Phase 롤백)
        └→ API-ANO-002  (stat_timeseries 행 없음 → 500)
            └→ FE-API-004  (FE_BLOCK)
```

### 파싱 실패 전파

```
PARSE-DATE-001  (DB DATE → YYYY-MM 변환 실패)
    └→ API-INT-001  (Pydantic 직렬화 예외 → 500)
        └→ FE-API-004  (FE_BLOCK)

PARSE-NUM-002  (API 응답 NaN 필드)
    └→ FE-D3-002  (D3 스케일 계산 실패)
        └→ FE_FALLBACK  (NaN 필터링 후 재렌더링)

PARSE-SCHEMA-001  (응답 envelope 구조 불일치)
    └→ FE_BLOCK  (해당 뷰 에러 UI 표시)
        ← 백엔드 API 응답 구조 변경 시 발생
        → 백엔드 api_spec 변경 이력 확인 필요
```

### Redis 캐시 실패 전파

```
DB-CACHE-001  (Redis 연결 실패)
    └→ WARN  (캐시 없이 DB 직접 조회 → 정상 응답)
        → 서비스 중단 없음. Redis 복구 후 자동 재개.

DB-CACHE-002  (Redis JSON 역직렬화 실패)
    └→ WARN  (해당 캐시 키 삭제 → DB 재조회)
        ← 배포 후 구 캐시와 신 스키마 불일치 시 발생
        → 배포 직후 Redis flush 권장

PARSE-REDIS-001  (API 레이어에서 Pydantic 검증 실패)
    └→ DB-CACHE-002와 동일 처리 (캐시 무효화 → DB 재조회)
        ← DB-CACHE-002와 감지 레이어만 다름
           DB-CACHE-002: Redis 레이어 / PARSE-REDIS-001: API Pydantic 레이어
```

### 배치 실패 전파

```
DB-TX-001  (Phase 적재 트랜잭션 실패)
    └→ API-BATCH-001  (배치 실패 기록)
        → pipeline_runs.status='failed'. 서버 유지.
        → 다음 배치(익월 15일) 재실행 시
            └→ DB-UNIQ-*  (재적재 중복) → UPSERT로 흡수

API-BATCH-002  (배치 중복 실행 감지)
    └→ WARN + 실행 skip
        ← 배치 락 미해제 상태에서 재기동 시 발생
```

### API → DB 역추적 가이드

| API 에러 코드 | 추적 대상 DB 코드 | 확인 방법 |
|---|---|---|
| `API-ANO-002` (stat 행 없음) | `DB-TX-001` (롤백 여부) | `pipeline_runs.status` 확인 |
| `API-COM-002` (분석 데이터 없음) | `DB-FK-001/002` (시드 미적재) | `commodities`, `segments` 테이블 확인 |
| `API-INT-001` (500 반복) | `DB-CONN-001/002` (DB 상태) | DB pool 상태·연결 로그 확인 |
| `FE-API-004` (FE_BLOCK 반복) | `PARSE-DATE-001`, `PARSE-ENUM-001` | API Pydantic serializer 로그 확인 |

---

## 4. 설계 문제점 연결

본 문서는 미결 설계 문제점과 예외 코드의 관계를 추적한다. 설계 문제점 해결 전에는 해당 코드의 처리 방침이 잠정적일 수 있다.

| 설계 문제점 | 관련 코드 | 해결 전 영향 |
|---|---|---|
| D-02 (신뢰도 등급 NULL 정책) | DB-NN-001 | 정책 미확정 시 FATAL이 빈번히 발생 |
| D-07 (breakpoints 변환 규칙) | DB-ARR-002, DB-TYPE-001 | 파싱 실패 시 WARN으로 관대 처리 중 |
| D-11 (월 식별자 변환) | DB-TYPE-001 | 정규화 레이어 부재 시 FATAL 유발 |
| D-12 (레이아웃 5 폴백) | API-LAY-002 | 3구간+레이아웃 5가 에러인지 폴백인지 미결 |
| D-13 (동월 복수 패턴) | DB-UNIQ-002 | UNIQUE 키 변경 시 UPSERT 규칙 재정의 필요 |

---

*이 문서는 설계 검토·구현 착수·디버깅 심층 분석 시 참조한다. 반복 코딩 세션에는 `exception_spec_v4.md`만 첨부한다.*
