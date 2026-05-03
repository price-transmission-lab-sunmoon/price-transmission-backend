# Frame 명세서 — backend

**문서 유형**: Frame 명세서 (v3)
**브랜치명**: `frame/backend`
**담당자**: 예병성 (sprint_plan_vN §3.2 기준)
**작성 기준 문서** (최신 버전 자동 참조 — `abcd_vN.md` 규칙):
- `doc1_technical_pipeline_vN.md`
- `web_plan_vN.md`
- `pipeline_output_spec_vN.md`
- `db_schema_vN.md`
- `api_spec_vN.md`
- `exception_spec_vN.md`

**작성일**: 2026-04-26
**상태**: 초안 / PM 승인 대기

**변경 이력**:
- v1 (2026-04-22): 초안 작성 (Sonnet 작성, 당시 기준 참조 문서 doc1 v8 · db_schema v2 · api_spec v3 · exception_spec v1).
- v2 (2026-04-26): 참조 문서 일괄 갱신 (당시 기준 doc1 v9 · db_schema v3 · api_spec v4 · exception_spec v2 · pipeline_output_spec v5). 담당자 정정(샤킬라→예병성). 상위 명세 정합성 보강 — `/api/v1` prefix 근거 명시, 더미 응답 출처 명시, 에러 envelope·예외 핸들러·Literal 타입 정책 신설. ORM 모델 분할 범위 명시(9개 테이블 우선). Alembic·로깅·smoke test·CORS 정책 추가.
- v2 → v3 (2026-05-02): 본문 정정. `reference_audit_report v1` §4 규칙에 따라 외부 참조 표기를 `abcd_vN.md`로 일괄 전환. 잔존 구버전 참조(당시 pipeline_output_spec v5, db_schema v3, exception_spec v2, doc1 v9) 전부 정정. 본 문서는 이제 `docs/docs_manifest.md`의 버전 해석기에 의해 자동 최신 참조되며, 파일명·본문은 `_v3`로 정합.

---

## 1. 완료 기준

이 Frame 명세의 완료는 아래 조건을 모두 충족한 시점으로 한다.

| 항목 | 조건 |
|------|------|
| 로컬 실행 | 더미 데이터 기준 오류 없이 `uvicorn` 기동 성공 |
| 진입점 응답 | `GET /api/v1/meta/config` 더미 응답 200 OK 반환 |
| 연결 확인 | PostgreSQL ping 성공, Redis ping 성공 (응답 본문 `db_status`/`redis_status` `"ok"`) |
| 타입 일치 | `db_schema_vN ↔ api_spec_vN ↔ Pydantic 스키마` 3방향 필드명 + Literal 값 일치 (불일치 0건) |
| 문서 첨부 | `docs/` 폴더에 명세 8종 + CLAUDE.md 사본 존재 |
| Smoke test | §7.4 정의 3건 모두 통과 |

---

## 2. 디렉토리 구조

> 모든 폴더·파일은 이 Frame PR 시점에 실제로 생성하여 커밋한다. 빈 폴더는 `.gitkeep`을 둔다.
> 모든 Python 패키지 폴더에는 빈 `__init__.py`를 명시적으로 생성한다.

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                       ← FastAPI 진입점 (lifespan, CORS, 라우터 등록)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                   ← 의존성 주입 (DB 세션·Redis 클라이언트)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py             ← APIRouter 통합 (prefix="/api/v1")
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── commodities.py    ← /commodities, /commodities/{id},
│   │           │                       /stream, /stream/minimap,
│   │           │                       /scatter, /raw-prices, /raw-prices/minimap
│   │           ├── anomalies.py      ← /anomalies/summary,
│   │           │                       /anomalies/{id}/detail,
│   │           │                       /stat-series, /stat-snapshot,
│   │           │                       /irf, /ml-map
│   │           └── meta.py           ← /meta/config (헬스),
│   │                                   /meta/pipeline, /meta/analysis-params,
│   │                                   /segments, /events, /freshness
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                 ← Pydantic Settings (§4 환경 변수 로딩)
│   │   ├── exceptions.py             ← ProjectError 계층 + 전역 핸들러
│   │   │                               (exception_spec_vN §부록 A 직접 구현)
│   │   └── logging.py                ← dictConfig 초기화 (§8.4)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                   ← SQLAlchemy DeclarativeBase, 메타데이터
│   │   ├── session.py                ← 비동기 세션 팩토리 (asyncpg)
│   │   └── models/                   ← Frame 단계 9개 테이블만 정의 (§8.6)
│   │       ├── __init__.py
│   │       ├── commodity.py          ← commodities, segments, external_events
│   │       ├── anomaly.py            ← anomaly_results, asymmetry_results
│   │       ├── timeseries.py         ← stat_timeseries, raw_prices
│   │       └── batch.py              ← pipeline_runs, data_freshness
│   ├── schemas/                      ← Pydantic 응답 DTO (api_spec_vN와 1:1)
│   │   ├── __init__.py
│   │   ├── commodity.py              ← /commodities, /commodities/{id}, /segments
│   │   ├── anomaly.py                ← /anomalies/summary, /anomalies/{id}/detail
│   │   ├── timeseries.py             ← 시계열 envelope + /stream, /scatter,
│   │   │                               /raw-prices, /stat-series 응답
│   │   ├── meta.py                   ← /meta/config, /freshness, /events
│   │   └── error.py                  ← ErrorBody, ErrorResponse (§6.4)
│   ├── services/                     ← Frame 단계 빈 상태. 후속 feat 추가 (§8.7)
│   │   └── .gitkeep
│   └── cache/
│       ├── __init__.py
│       └── redis.py                  ← Redis 클라이언트 초기화·ping
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_frame_tables.py    ← 9개 테이블 수동 작성 (§8.5)
│       └── 0002_seed_reference_data.py     ← 시드 적재 (commodities 10·segments 5·events 5)
├── tests/
│   ├── __init__.py
│   └── test_frame_smoke.py           ← §7.4 smoke test 3건
├── docs/                             ← 명세 8종 + CLAUDE.md 사본
│   ├── doc1_technical_pipeline_vN.md
│   ├── doc3_research_proposal_vN.md
│   ├── web_plan_vN.md
│   ├── pipeline_output_spec_vN.md
│   ├── db_schema_vN.md
│   ├── api_spec_vN.md
│   ├── exception_spec_vN.md
│   ├── sprint_plan_vN.md
│   └── CLAUDE.md
├── .env.example
├── .gitignore
├── .python-version                   ← `3.11.9`
├── alembic.ini
├── pyproject.toml                    ← ruff·pytest·alembic 설정 전용 (§3 마지막)
├── requirements.txt                  ← 의존성 SoT, 정확 버전 고정 (§3)
├── CLAUDE.md                         ← AI 컨텍스트 기준 파일 (최신 버전)
└── README.md                         ← 사람 대상 진입점 (실행 방법·구조 요약)
```

---

## 3. 기술 스택 및 버전 고정

모든 패키지는 `requirements.txt`에 **정확한 버전**(예: `fastapi==0.111.0`)으로 명시한다. 버전 범위 연산자(`>=`, `~=`, `^`) 사용 금지.

| 패키지 / 도구 | 버전 | 출처 |
|---|---|---|
| Python | 3.11.9 | 본 Frame 명세 §3 단독 정의 |
| fastapi | 0.111.0 | 본 Frame 명세 §3 단독 정의 |
| uvicorn[standard] | 0.29.0 | 본 Frame 명세 §3 단독 정의 |
| sqlalchemy | 2.0.30 | db_schema_vN §DB 구성 (SQLAlchemy 2.0 비동기) |
| asyncpg | 0.29.0 | SQLAlchemy 비동기 드라이버 |
| alembic | 1.13.1 | 본 Frame 명세 §3 단독 정의 |
| pydantic | 2.7.1 | api_spec_vN §공통 사항 (Pydantic v2 serializer) |
| pydantic-settings | 2.2.1 | exception_spec_vN §6 CFG-CORE-* 설정 로딩 |
| redis | 5.0.4 | db_schema_vN §DB 구성 (Redis 캐싱) |
| apscheduler | 3.10.4 | feat/batch-scheduler 선반영 |
| statsmodels | 0.14.2 | doc1_vN §8 (≥0.14 → 정확 버전 고정) |
| scikit-learn | 1.4.2 | doc1_vN §8 (≥1.4) |
| ruptures | 1.1.9 | doc1_vN §8 (≥1.1) |
| scipy | 1.11.4 | doc1_vN §8 (≥1.11) |
| pandas | 2.2.2 | doc1_vN §8 (≥2.0) |
| numpy | 1.26.4 | doc1_vN §8 (≥1.24) |
| httpx | 0.27.0 | 비동기 테스트 클라이언트 |
| pytest | 8.2.0 | 테스트 |
| pytest-asyncio | 0.23.6 | 비동기 테스트 |
| ruff | 0.4.4 | 린트·포맷 (§8.8) |

> **고정 원칙**: 위 표의 모든 버전은 Frame 생성 시점(2026-04-24~28) 기준 안정 버전을 적용한다. 이 Frame 머지 이후 **feat/* 브랜치에서 버전을 임의로 상향·하향할 수 없다**. 변경이 필요하면 별도 Feature 명세를 작성하고 PM 승인을 받는다.
>
> **doc1_vN §8과의 관계**: doc1_vN §8은 파이프라인 분석 라이브러리만 권장 버전(범위)으로 제시한다. 본 Frame 명세는 이를 정확 버전으로 고정하고, doc1에 부재한 백엔드 패키지(FastAPI, SQLAlchemy, alembic, redis-py 등)를 단독으로 확정한다.
>
> **`pyproject.toml` vs `requirements.txt`**: 의존성 SoT는 **`requirements.txt`**다. `pyproject.toml`은 **ruff·pytest·alembic 도구 설정 전용**이며 의존성을 중복 작성하지 않는다.

---

## 4. 환경 변수 목록

`app/core/config.py`의 Pydantic Settings로 로딩한다. `.env.example`에 아래 변수를 모두 포함하고, `.env`는 `.gitignore`로 제외한다.

| 변수명 | 설명 | 필수 | 기본값 | 예외 코드 |
|---|---|:---:|---|---|
| `DATABASE_URL` | PostgreSQL 비동기 연결 문자열 (`postgresql+asyncpg://...`) | 필수 | — | `CFG-CORE-001` |
| `REDIS_URL` | Redis 연결 문자열 | 필수 | — | `CFG-CORE-001` |
| `APP_ENV` | 실행 환경 (`development` \| `production`) | 선택 | `development` | — |
| `LOG_LEVEL` | 로그 레벨 (`DEBUG` \| `INFO` \| `WARNING` \| `ERROR`) | 선택 | `INFO` | — |
| `CORS_ALLOWED_ORIGINS` | 콤마 구분 origin 목록 | 선택 | `http://localhost:5173` | — |
| `ROLLING_WINDOW` | 롤링 윈도우 기간 (월) | 선택 | `48` | `CFG-CORE-003` |
| `CONTAMINATION` | ML 이상 비율 | 선택 | `0.10` | `CFG-CORE-003` |
| `RANDOM_STATE` | ML 난수 시드 | 선택 | `42` | `CFG-CORE-003` |

> **시크릿 금지**: JWT 시크릿·DB 패스워드 등을 코드에 하드코딩 금지. 프론트엔드 전용 변수(`VITE_*`)는 본 파일에 포함하지 않는다.
>
> **ROLLING_WINDOW / CONTAMINATION / RANDOM_STATE 값 출처**: pipeline_output_spec_vN §파라미터 표 (`settings.py` 위치).

---

## 5. DB 연결 방식

| 항목 | 내용 |
|---|---|
| ORM | SQLAlchemy 2.0 비동기 (`asyncpg` 드라이버) |
| 커넥션 풀 크기 | `pool_size=10`, `max_overflow=20` |
| 쿼리 타임아웃 | 30초 (`statement_timeout`) |
| 트랜잭션 단위 | Phase 적재 단위로 단일 트랜잭션. 실패 시 해당 Phase 롤백 (db_schema_vN §설계 원칙 7, D-17) |
| 월 식별자 변환 | Pydantic **serializer** — `DATE` → `YYYY-MM` (`strftime("%Y-%m")`) 출력. **field_validator** — 입력 시 `YYYY-MM` 형식 강제. **api_spec_vN §공통 사항 (D-11) 정책 직접 구현** |
| `period` 입력 검증 | `field_validator`에서 `YYYY-MM` 파싱 후 `date(y, m, 1)`로 정규화. `YYYY-MM-DD` 형식이면서 `day != 1`인 경우 `DB-TYPE-001` 발생 (FATAL). **db_schema_vN §설계 원칙 6 (월초 강제) 직접 대응** |
| 부팅 sanity check | `app.main` lifespan에서 DB·Redis ping 수행. 실패 시 `CFG-CORE-001` (FATAL). **단, `APP_ENV=development`에서는 WARN 후 기동** (DB 없는 더미 응답 시나리오 지원) |
| ORM ↔ Pydantic 매핑 | `app/schemas/`는 응답 전용 DTO. **endpoint에서 ORM 모델을 직접 반환 금지** — 반드시 service 함수에서 명시적 변환. `from_attributes=True` 허용하되 relationship lazy load는 await로 해소된 상태여야 함 |

---

## 6. 타입 정의 파일 위치

| 항목 | 경로 | 대응 관계 |
|---|---|---|
| 백엔드 Pydantic 스키마 | `app/schemas/` | `api_spec_vN.md` response 1:1 대응 |
| 프론트엔드 TypeScript 타입 | `src/types/` (frontend repo) | 백엔드 Pydantic 스키마 1:1 대응 |
| 검증 시점 | Frame 머지 직전 PM 게이트 체크 | PM이 3방향 필드명 + Literal 값 일치 확인 |

### 6.1 필드명 표기 정책

백엔드 Pydantic 필드명은 **DB 컬럼명을 변형 없이 `snake_case`로 유지**한다.

- **근거**: `team_ai_collab_vN §3.3` "필드명 드리프트 방지" 원칙.
- **구현 제약**: Pydantic v2 `model_config`에서 `populate_by_name=True` 설정 가능. 단 `alias_generator`(camelCase 변환) **금지**. FastAPI 응답 직렬화 시 필드명 변환 설정 금지.

### 6.2 3방향 필드명·타입 일치 필수 확인 목록

이 Frame 머지 전 PM이 `db_schema_vN.md` → `api_spec_vN.md` → `app/schemas/` 순으로 대조하여 불일치 0건을 확인한다.

| db_schema_vN 컬럼 / 정책 | api_spec_vN JSON 키 | Pydantic 필드 |
|---|---|---|
| `commodity_id` | `commodity_id` | `commodity_id: str` |
| `segment_id` | `segment_id` | `segment_id: str` |
| `period` (DATE 월초) | `period` (`YYYY-MM`) | `period: str` (validator 적용) |
| `cluster` | `cluster` | `cluster: Literal['grain','oil_sugar','tropical','livestock','independent']` |
| `route_type` | `route_type` | `route_type: Literal['3seg','4seg']` |
| `confidence_grade` | `confidence_grade` | `confidence_grade: Literal['high','medium','reference']` |
| `primary_pattern` | `primary_pattern` | `primary_pattern: Literal['pattern1','pattern2','pattern3']` |
| `pattern_types` (배열) | `pattern_types` (배열) | `pattern_types: list[Literal['pattern1','pattern2','pattern3']]` |
| `model_params.model_type` | `segment_meta.{seg}.model_type` | `model_type: Literal['VAR','VECM']` |
| `stat_timeseries.ect_type` | `ect_type` (패널 응답) | `ect_type: Literal['ECT','log_spread'] \| None` |
| `transmission_rate` | `transmission_rate` | `transmission_rate: float \| None` |
| `is_new` | `is_new` | `is_new: bool` |
| `anomaly_id` (← `anomaly_results.id`) | `anomaly_id` | `anomaly_id: int` |
| `pipeline_runs.status` (내부) | (응답 미노출) | `status: Literal['running','completed','failed']` |
| (envelope) | `granularity` | `granularity: Literal['monthly','quarterly','yearly']` |
| (envelope) | `requested_from`/`requested_to`/`actual_from`/`actual_to` | `str` (YYYY-MM, validator) |
| (envelope) | `total_points` | `total_points: int` |

### 6.3 Literal 타입 사용 원칙

고정 enum 성격의 문자열 필드는 **반드시 `typing.Literal[...]`**로 선언한다.

- **값 목록 출처**: `db_schema_vN`의 컬럼 코멘트 (예: `'high' | 'medium' | 'reference'`)
- **DB CHECK 제약 부재 보완**: db_schema_vN은 CHECK 제약을 두지 않으므로 Pydantic Literal로 입출력 양쪽 모두 강제
- **검증 실패 시**: 응답 422 (`API-VAL-001`)

### 6.4 에러 응답 envelope 스키마

`api_spec_vN §공통 사항` + `exception_spec_vN §부록 A` 직접 구현. 모든 에러 응답은 본 envelope를 사용한다.

```python
# app/schemas/error.py
from pydantic import BaseModel

class ErrorBody(BaseModel):
    code: str                    # 외부 코드: 'COMMODITY_NOT_FOUND', 'INVALID_SEGMENT' 등
    message: str
    context: dict | None = None  # D-20: 디버깅 컨텍스트 (검증 실패 필드, 요청 파라미터 등)

class ErrorResponse(BaseModel):
    error: ErrorBody
```

외부 코드 목록은 **api_spec_vN §에러 코드 정의** (13종) + `INTERNAL_ERROR` 1종을 사용한다. 신규 코드 추가는 `exception_spec_vN §8` 규칙을 따른다.

### 6.5 날짜·시각 직렬화 정책

| 필드 종류 | 직렬화 형식 | 예 |
|---|---|---|
| `period` (DATE 월) | `YYYY-MM` | `"2026-03"` |
| `start_date` / `end_date` 등 (DATE 일) | `YYYY-MM-DD` | `"2022-02-15"` |
| `created_at` / `last_updated` 등 (TIMESTAMPTZ) | ISO 8601 UTC `Z` 접미사 | `"2026-04-01T03:00:00Z"` |

**근거**: api_spec_vN §공통 사항 D-11 — 응답 시각은 UTC 고정.

---

## 7. 로컬 실행 확인 기준

### 7.1 사전 준비

- [ ] Python 3.11.9 설치 확인 (`python --version` == `3.11.9`)
- [ ] PostgreSQL 16 실행 중
- [ ] Redis 실행 중
- [ ] `.env.example` 복사하여 `.env` 생성, `DATABASE_URL`·`REDIS_URL` 설정
- [ ] `pip install -r requirements.txt` 성공
- [ ] `docs/` 폴더 내 명세 8종 + CLAUDE.md 존재

### 7.2 실행 확인

- [ ] `uvicorn app.main:app --reload --port 8000` 오류 없이 기동
- [ ] `GET /api/v1/meta/config` 200 OK, `db_status: "ok"`, `redis_status: "ok"`
- [ ] `GET /api/v1/commodities` 200 OK, 10종 품목 배열 반환
- [ ] `GET /api/v1/segments` 200 OK, 5개 구간 반환
- [ ] `GET /api/v1/freshness` 200 OK
- [ ] `alembic upgrade head` 오류 없음 (초기 9개 테이블 + 시드 적재)
- [ ] `pytest` 실행 시 §7.4 smoke test 3건 통과

### 7.3 실행 스크립트

| 스크립트 | 명령 | 용도 |
|---|---|---|
| `dev` | `uvicorn app.main:app --reload --port 8000` | dev 서버 |
| `migrate` | `alembic upgrade head` | DB 마이그레이션 적용 |
| `migrate:rollback` | `alembic downgrade -1` | 1단계 롤백 |
| `test` | `pytest` | 전체 테스트 |
| `lint` | `ruff check .` | Ruff 린트 |
| `format` | `ruff format .` | Ruff 포맷 |
| `format:check` | `ruff format --check .` | Ruff 포맷 검증 |

### 7.4 Frame 단계 smoke test 범위

`tests/test_frame_smoke.py`에 다음 3건만 작성한다. 계량·ML·실 DB 통합 테스트는 모두 feat 단계.

1. **`test_app_startup`**: `httpx.AsyncClient`로 앱 기동, `GET /api/v1/meta/config` 200 응답 + 본문에 `app_env`, `db_status`, `redis_status`, `frame_version` 키 모두 존재
2. **`test_commodities_dummy`**: `GET /api/v1/commodities` 응답이 10개 품목 배열, 각 행에 `commodity_id`, `cluster`, `route_type`, `segments` 키 존재. `cluster` 값은 §6.2 Literal 5종 중 하나, `route_type`은 `'3seg'` 또는 `'4seg'`
3. **`test_period_validator`**: `POST` 또는 `query`로 `'2026-3'`(zero-pad 없음), `'2026-03-15'`(월초 아님) 입력 시 422 응답. `error.code == 'INVALID_DATE_RANGE'` 또는 `'API-VAL-001'`

---

## 8. 기타

### 8.1 더미 응답 정책

각 엔드포인트는 `app/schemas/`의 Pydantic 모델을 import하여 더미값을 채워 반환한다. **더미값 출처는 명시적으로 명세 문서를 참조**하며 임의 창작 금지.

| 엔드포인트 | 더미값 출처 |
|---|---|
| `GET /api/v1/commodities` | **db_schema_vN §`commodities` 초기 데이터 표 (10행)** 그대로 |
| `GET /api/v1/commodities/{id}` | 위 10행 중 일치 행 + `segment_meta` 빈 객체 `{}` |
| `GET /api/v1/segments` | **db_schema_vN §`segments` 초기 데이터 표 (5행)** 그대로 |
| `GET /api/v1/events` | **db_schema_vN §`external_events` 초기 데이터 표 (5행)** 그대로 |
| `GET /api/v1/freshness` | 고정값 `{"data_up_to": "2026-03", "next_run_date": "2026-04-15", "last_updated": "2026-04-01T03:00:00Z"}` |
| `GET /api/v1/meta/config` | §8.2 정의 |
| `GET /api/v1/meta/pipeline` / `analysis-params` | 빈 배열 또는 빈 객체 |
| 시계열·패널 엔드포인트 (`/stream`, `/scatter`, `/anomalies/{id}/*` 등) | envelope만 채우고 `series`/`anomalies` 등 데이터 배열은 빈 배열. feat 단계에서 실 DB 연결 |

DB가 없어도 더미 응답으로 동작해야 한다 (`APP_ENV=development` 분기, §5).

### 8.2 헬스체크 엔드포인트 — `GET /api/v1/meta/config`

api_spec_vN에 없는 frame 단계 신설 엔드포인트. **본 Frame 명세서가 단독 권위 출처**이며, frame 머지 후 api_spec에 추가 반영을 PM에게 요청한다.

```json
{
  "app_env": "development",
  "db_status": "ok",
  "redis_status": "ok",
  "frame_version": "0.1.0"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `app_env` | `Literal['development','production']` | `APP_ENV` 환경 변수 echo |
| `db_status` | `Literal['ok','down']` | PostgreSQL ping 결과 |
| `redis_status` | `Literal['ok','down']` | Redis ping 결과 |
| `frame_version` | `str` | `pyproject.toml` 버전 echo |

### 8.3 라우터 prefix 정책

api_spec_vN §공통 사항이 `Base URL = /api/v1`을 명시한다. 본 Frame 명세는 다음을 확정한다.

- FastAPI 라우터는 `app/api/v1/router.py`에서 모든 endpoint를 통합하여 `prefix="/api/v1"`로 마운트
- api_spec_vN의 모든 경로는 `/api/v1` prefix를 붙여 노출 (예: `/commodities` → `/api/v1/commodities`)
- 라우터 `include_router` 호출은 endpoint 그룹별로 분리 (`commodities`, `anomalies`, `meta`)

### 8.4 전역 예외 핸들러 정책

`exception_spec_vN §부록 A` 예외 클래스 계층을 `app/core/exceptions.py`에 그대로 정의하고, FastAPI `add_exception_handler`로 전역 등록한다.

```python
# app/core/exceptions.py 골격 (exception_spec_vN §부록 A 직접 구현)
class ProjectError(Exception):
    code: str
    message: str
    context: dict

class PipelineError(ProjectError):       # PL-*
    phase: str

class DBError(ProjectError):              # DB-*
    table: str | None = None

class APIError(ProjectError):             # API-*
    http_status: int
    public_code: str   # api_spec_vN §에러 코드 정의의 외부 코드

class ConfigError(ProjectError):          # CFG-*
    pass

class ExternalAPIError(ProjectError):     # EXT-*
    source: str
    retry_count: int
```

**핸들러 매핑**:

| 캐치 대상 | HTTP | 응답 `error.code` | 비고 |
|---|---|---|---|
| `APIError` | `exc.http_status` | `exc.public_code` | api_spec_vN §에러 코드 정의 13종 직접 매핑 |
| `RequestValidationError` (Pydantic) | 400 | `API-VAL-001` | `context.loc` / `context.input` 보존 |
| `PipelineError` / `DBError` / `ExternalAPIError` | 500 | `INTERNAL_ERROR` | **내부 코드 사용자 노출 금지** (exception_spec_vN §5 API-INT-001) |
| `ConfigError` | (부팅 중단) | — | FATAL, 앱 기동 실패 |
| 기타 `Exception` | 500 | `INTERNAL_ERROR` | 동일 |

모든 예외는 `extra={"error_code": exc.code, "context": exc.context}`로 구조화 로깅한다.

### 8.5 로깅 구성

`app/core/logging.py`에서 `dictConfig`로 초기화. 표준 출력에 **JSON 1줄 포맷**으로 기록 (exception_spec_vN §부록 A 예시).

```json
{"ts": "2026-04-26T10:00:00Z", "level": "ERROR", "code": "PL-P2-003",
 "msg": "ADF 회귀 실패", "phase": "2",
 "context": {"commodity_id": "wheat", "column": "ppi"}}
```

- `LOG_LEVEL` 환경 변수로 레벨 조절
- `app.main` lifespan 시작 시점에 호출
- exception 핸들러가 `extra={"error_code": ..., "context": ...}`로 로그 보강

### 8.6 ORM 모델 분할 범위 (Frame 단계)

db_schema_vN는 총 19개 테이블 + 1개 머티리얼라이즈드 뷰를 정의한다. Frame 단계는 그 중 **9개 테이블만 우선 정의**한다. 나머지는 해당 feat 브랜치에서 추가.

| 파일 | 포함 테이블 | feat 브랜치 |
|---|---|---|
| `commodity.py` | `commodities`, `segments`, `external_events` | (Frame 포함) |
| `anomaly.py` | `anomaly_results`, `asymmetry_results` | (Frame 포함) |
| `timeseries.py` | `stat_timeseries`, `raw_prices` | (Frame 포함) |
| `batch.py` | `pipeline_runs`, `data_freshness` | (Frame 포함) |
| (신규) | `stationarity_results`, `cointegration_results` | `feat/pipeline-phase2-3` |
| (신규) | `model_params`, `irf_data`, `baselines`, `granger_results` | `feat/pipeline-phase4-5` |
| (신규) | `breakpoints`, `subperiods` | `feat/pipeline-phase6-7` |
| (신규) | `ml_scores`, `ml_projections` | `feat/pipeline-phase7-ml` |
| (신규) | `mv_anomaly_density_yearly` | `feat/redis-cache` 또는 별도 |

### 8.7 `app/services/` 향후 분할 예고

Frame 단계는 `app/services/.gitkeep` 빈 상태 유지. 후속 feat 브랜치에서 다음 모듈 추가 예정.

```
app/services/
├── stream.py            ← /commodities/{id}/stream 비즈니스 로직 (feat/api-endpoints)
├── anomaly_detail.py    ← /anomalies/{id}/detail 패널 통합 (4테이블 조인) (feat/api-endpoints)
├── ml_projection.py     ← /anomalies/{id}/ml-map (OI-15 확정 후, feat/pipeline-phase7-ml)
└── batch.py             ← APScheduler 월 배치 (feat/batch-scheduler)
```

### 8.8 `pyproject.toml` 도구 설정

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]   # line-too-long은 formatter에 위임

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 8.9 Alembic 초기화 정책

Frame 단계의 마이그레이션은 **수동 작성 2개 revision**으로 한정한다. **autogenerate 사용 금지** — §8.6의 9개 테이블 외 미정의 테이블 누락 위험.

| 파일 | 내용 |
|---|---|
| `alembic/versions/0001_initial_frame_tables.py` | §8.6의 9개 테이블 + 모든 인덱스 + UNIQUE 제약 |
| `alembic/versions/0002_seed_reference_data.py` | `commodities` 10행 + `segments` 5행 + `external_events` 5행 (db_schema_vN §초기 데이터) |

후속 feat 브랜치는 추가 테이블별로 별도 revision을 작성한다.

### 8.10 CORS 설정

```python
# app/main.py (요지)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

기본값 `http://localhost:5173` (프론트엔드 dev 서버). 프로덕션 origin은 배포 명세에서 별도 정의.

### 8.11 ML 파이프라인 구현 범위

이상 탐지·ML 투영 등 핵심 ML 로직(doc1_vN §3~§7)은 본 Frame에서 **구현하지 않는다**. `app/services/`는 빈 상태로 두고 후속 feat 브랜치(`feat/pipeline-phase7-ml`, `feat/api-endpoints` 등)에서 구현.

### 8.12 담당 체계

- **Frame 작성·구현·PR 제출**: 예병성 (sprint_plan_vN §3.2 기준)
- **후속 feat 단계 백엔드 협업자**: 예병성 (계량·DB·API 주도, sprint_plan_vN §4~5), 하대수 (DB 연결·배치 스케줄러·Redis, sprint_plan_vN §5~7), 바게스타니 샤킬라 (분석 수치 패널·온보딩 영역에서 백엔드 응답 협업)

### 8.13 절대 금지 사항

| 금지 사항 | 이유 |
|---|---|
| `requirements.txt`에 버전 범위 연산자(`>=`, `~=`, `^`) 사용 | 재현성 파괴 |
| JWT 시크릿·DB 패스워드 하드코딩 | 보안 |
| API 응답 필드명을 camelCase로 변환 (`alias_generator`) | §6.1 정책 위반, 3방향 일치 파괴 |
| 프론트엔드 전용 환경 변수(`VITE_*`)를 `.env.example`에 추가 | 책임 분리 위반 |
| ORM 모델을 endpoint 응답으로 직접 반환 | §5 정책 위반, 직렬화 일관성 파괴 |
| Alembic `autogenerate` 사용 (Frame 단계) | §8.6에 정의되지 않은 테이블 누락 위험 |
| 명세 8종에 부재한 외부 에러 코드 임의 생성 | exception_spec_vN §8 규칙 위반 |
| `app/services/`에 Frame 단계 비즈니스 로직 작성 | §8.11 위반 |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 디렉토리 구조가 db_schema_vN·api_spec_vN와 정합한가 | ☐ |
| 패키지 버전이 전체 고정되어 있는가 (버전 범위 연산자 0건) | ☐ |
| 필수 환경 변수가 모두 정의되어 있는가 | ☐ |
| 로컬 실행 확인 기준이 구체적인가 (smoke test 3건 포함) | ☐ |
| 타입 정의 3방향 일치 경로 + Literal 값 목록이 명시되어 있는가 | ☐ |
| 명세 8종 + CLAUDE.md `docs/` 폴더 첨부 정책이 명시되어 있는가 | ☐ |
| 더미 응답 출처가 db_schema_vN §초기 데이터로 명시되어 있는가 | ☐ |
| 전역 예외 핸들러 매핑이 exception_spec_vN §부록 A와 일치하는가 | ☐ |
| ORM 모델 분할 범위가 Frame/feat 경계 기준으로 명시되어 있는가 | ☐ |

**승인일**: YYYY-MM-DD
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `frame/backend` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: frame/backend
- **Frame 명세**: `docs/frame_spec_backend_v2.md`
- **담당자**: 예병성

## 구현 완료 항목
- [ ] 디렉토리 구조 생성 (§2 기준, `__init__.py` 모두 포함)
- [ ] 기술 스택 버전 고정 — `requirements.txt` 정확 버전, 범위 연산자 0건 (§3)
- [ ] 환경 변수 `.env.example` 작성 (§4, CORS_ALLOWED_ORIGINS 포함)
- [ ] DB/Redis 연결 확인, lifespan sanity check 동작 (§5)
- [ ] Pydantic 스키마 초기 작성 (§6, Literal 타입 적용)
- [ ] 에러 envelope 스키마 + 전역 예외 핸들러 작성 (§6.4, §8.4)
- [ ] ORM 모델 9개 테이블 정의 (§8.6)
- [ ] Alembic revision 2개 작성 (§8.9)
- [ ] 로컬 실행 확인 (§7.2)
- [ ] Smoke test 3건 통과 (§7.4)

## 3방향 타입 일치 확인
- [ ] `db_schema_vN.md` ↔ `api_spec_vN.md` ↔ `app/schemas/` 필드명 일치
- [ ] Literal 값 목록 일치 (`cluster`, `route_type`, `confidence_grade`, `primary_pattern`, `model_type`, `granularity`, `ect_type`, `pipeline_runs.status`)
- [ ] snake_case 필드명 유지 (§6.1, alias 변환 없음)
- 불일치 항목: {없음 / 목록}

## 포함된 문서
- [ ] `docs/` 폴더에 명세 8종 사본 첨부 (doc1_vN, doc3_vN, web_plan_vN, pipeline_output_spec_vN, db_schema_vN, api_spec_vN, exception_spec_vN, sprint_plan_vN)
- [ ] `CLAUDE.md` 최신 버전 첨부
- [ ] `README.md` 초기 작성

## 로컬 실행 증빙
- `uvicorn` 실행 로그
- `GET /api/v1/meta/config` 응답 (`db_status: "ok"`, `redis_status: "ok"`)
- `GET /api/v1/commodities` 응답 (10행)
- `alembic upgrade head` 로그
- `pytest` smoke test 3건 통과 로그

## 리뷰어 확인 요청 사항
- snake_case 필드명 정책 최종 승인 (§6.1)
- Literal 타입 사용 원칙 최종 승인 (§6.3)
- `/api/v1/meta/config` 신설 엔드포인트 → api_spec 반영 일정 협의 (§8.2)
- 더미 응답 출처 정책 (db_schema_vN §초기 데이터 직접 사용) 최종 승인 (§8.1)

## 기타
- ML 비즈니스 로직 미구현 (§8.11)
- ORM 모델 9개 우선 정의, 나머지 10개 + mv 1개는 feat 단계 추가 (§8.6)
```
