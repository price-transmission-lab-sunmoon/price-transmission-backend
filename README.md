# price-transmission-backend

계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지 — FastAPI 백엔드

---

## 브랜치 구조

| 브랜치 | 설명 |
|---|---|
| `main` | 안정 브랜치 |
| `backend/merge_all` | 백엔드 전체 기능 통합 브랜치 (현재 최신) |
| `feat/be-*` | 기능별 개발 브랜치 (병합 완료) |
| `feat/pipeline-*` | 파이프라인 목업 → 실데이터 교체 브랜치 (진행 예정) |

---

## 사전 준비

- Python 3.11.9
- PostgreSQL 16
- Redis 7+

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경 변수 설정 (.env 파일 생성)
cp .env.example .env
# .env 에서 아래 두 항목 필수 설정:
#   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/<db>
#   REDIS_URL=redis://localhost:6379/0
```

### .env 전체 변수 목록

```dotenv
# 필수
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/price_transmission
REDIS_URL=redis://localhost:6379/0

# 선택 (기본값 있음)
APP_ENV=development          # development | production
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR
CORS_ALLOWED_ORIGINS=http://localhost:5173

# 파이프라인 적재
PIPELINE_DATA_ROOT=data/processed   # 파이프라인 CSV/JSON 출력 루트
DB_POOL_SIZE=10

# 배치 스케줄
BATCH_SCHEDULE_DAY=15        # 매월 몇 일 실행
BATCH_SCHEDULE_HOUR=3        # 실행 시각 (KST 기준)
BATCH_SCHEDULE_TZ=Asia/Seoul

# Redis 캐싱
REDIS_TTL=3600
REDIS_CACHE_PREFIX=pricelens
```

> **`APP_ENV=development`** 시: PostgreSQL·Redis 연결 실패해도 서버 기동 (WARN 로그만 출력).  
> **`APP_ENV=production`** 시: 연결 실패 시 `CFG-CORE-001` FATAL, 기동 중단.

---

## 서버 실행

```bash
# DB 마이그레이션 먼저 적용
alembic upgrade head

# 개발 서버 (hot-reload)
uvicorn app.main:app --reload --port 8000

# 프로덕션
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

서버 기동 후 확인:
- Swagger UI: `http://localhost:8000/docs`
- 헬스체크: `GET http://localhost:8000/api/v1/meta/config`

---

## 주요 명령

| 목적 | 명령 |
|---|---|
| 개발 서버 | `uvicorn app.main:app --reload --port 8000` |
| DB 마이그레이션 적용 | `alembic upgrade head` |
| 마이그레이션 1단계 롤백 | `alembic downgrade -1` |
| 테스트 실행 | `pytest` |
| 특정 테스트 파일 | `pytest tests/test_api_reference.py -v` |
| 린트 | `ruff check .` |
| 포맷 | `ruff format .` |

---

## API 엔드포인트 (Base: `/api/v1`)

### 참조 데이터
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/commodities` | 품목 목록 (10개) |
| GET | `/commodities/{id}` | 품목 상세 + 구간 메타 |
| GET | `/segments` | 분석 구간 정의 (ETag 캐싱) |
| GET | `/events` | 외부 충격 이벤트 (ETag 캐싱) |
| GET | `/freshness` | 데이터 기준 시점 |

### 시각화
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/commodities/{id}/stream` | 스트림 그래프 시계열 (Redis 캐싱) |
| GET | `/commodities/{id}/stream/minimap` | 스트림 미니맵 |
| GET | `/commodities/{id}/scatter` | 전달 구조 산점도 |
| GET | `/commodities/{id}/raw-prices` | 원시 시계열 레이아웃 1~6 (Redis 캐싱) |
| GET | `/commodities/{id}/raw-prices/minimap` | 원시 시계열 미니맵 |

### 이상 탐지
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/anomalies/summary` | 이달의 이상 요약 배너 |
| GET | `/anomalies/{id}/detail` | 패널 상세 (501 스텁 — phase7-stat 이후 구현) |
| GET | `/anomalies/{id}/stat-series` | 지표별 인라인 시계열 (Redis 캐싱) |
| GET | `/anomalies/{id}/stat-snapshot` | IQR/비대칭 스냅샷 |
| GET | `/anomalies/{id}/irf` | IRF 차트 |
| GET | `/anomalies/{id}/ml-map` | ML 결과맵 2D 투영 |

### 메타 / 배치
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/meta/config` | 헬스체크 (DB·Redis 상태) |
| GET | `/meta/pipeline` | 파이프라인 플로우 (ETag 캐싱) |
| GET | `/meta/analysis-params` | 파이프라인 파라미터 기준값 (ETag 캐싱) |
| POST | `/admin/batch/trigger` | 개발용 수동 배치 트리거 (202 비동기) |

---

## 디렉토리 구조

```
app/
├── main.py                  FastAPI 진입점 (lifespan, CORS, 에러 핸들러)
├── api/v1/
│   ├── router.py            라우터 등록
│   └── endpoints/
│       ├── commodities.py   참조·시각화 엔드포인트
│       ├── anomalies.py     이상 탐지·패널 엔드포인트
│       └── meta.py          메타·배치 엔드포인트
├── core/
│   ├── config.py            환경 변수 설정 (pydantic-settings)
│   ├── exceptions.py        예외 클래스 + 에러 체이닝 + 전역 핸들러
│   └── logging.py           JSON 구조화 로깅
├── db/
│   ├── session.py           AsyncEngine, AsyncSessionLocal
│   ├── models/              SQLAlchemy ORM 모델
│   └── loader/              파이프라인 CSV→DB 적재 (Phase 2~6)
├── schemas/                 Pydantic 응답 DTO
├── services/                비즈니스 로직
│   ├── reference.py         품목·구간·이벤트·freshness DB 조회
│   ├── stream.py            스트림 시계열 서비스
│   ├── raw_prices.py        원시 시계열 서비스
│   ├── scatter.py           산점도 서비스
│   ├── anomaly_summary.py   이상 요약 서비스
│   ├── anomaly_panel.py     패널 서비스 (501 스텁)
│   ├── meta.py              파이프라인 메타 서비스
│   └── batch.py             APScheduler 월별 배치
└── cache/
    └── redis.py             Redis 클라이언트 + cache_get/set/delete 헬퍼

alembic/                     DB 마이그레이션 (7개 revision)
tests/                       pytest 테스트 (DB·Redis 없이 실행 가능)
docs/                        명세 문서 (버전 관리: docs_manifest.md)
```

---

## 테스트

모든 테스트는 실 DB·Redis 없이 `AsyncMock`/`unittest.mock.patch`로 실행됩니다.

```bash
pytest tests/ -v
```

| 테스트 파일 | 검증 대상 |
|---|---|
| `test_frame_smoke.py` | 서버 기동, `/meta/config`, YYYY-MM 스키마 validator |
| `test_api_reference.py` | 참조 엔드포인트 전체 (commodities/segments/events/freshness) |
| `test_db_pipeline.py` | DB 적재 로직 (Phase 2/6, 타입 변환, 롤백, runner) |
| `test_redis_cache.py` | Redis 캐시 헬퍼 (HIT/MISS, DB-CACHE-001/002, invalidate) |

---

## 에러 디버깅

에러 발생 시 로그에 `error_code` 필드가 기록됩니다.  
코드 → 원인·처리 방침 조회: [`docs/exception_spec_v6.md`](docs/exception_spec_v6.md)  
에러 전파 경로 분석: [`docs/exception_design_v3.md`](docs/exception_design_v3.md)

```
# 로그 예시
ORIGIN  [DB-CONN-002] SQLAlchemy async pool 고갈 | context: {pool_size=10, active=10}
        └─ [API-INT-001] 내부 예외 처리 실패
```

---

## Pipeline 브랜치와 병합 방법

현재 `backend/merge_all`은 파이프라인 DB 적재 로직이 **목업(더미 데이터)** 상태입니다.  
`feat/pipeline-*` 브랜치에서 실제 파이프라인 출력 CSV/JSON을 읽어 DB에 적재하는 로직으로 교체합니다.

### 교체 대상

| 파일 | 현재 상태 | 교체 내용 |
|---|---|---|
| `app/services/batch.py` `_run_phase()` | 더미 로그만 출력 | `app/db/loader/runner.py`의 `run_pipeline()` 호출로 교체 |
| `app/db/loader/phase2.py` | `stationarity_results.csv` 읽기 구현 완료 | 실 CSV 경로 확인 후 `PIPELINE_DATA_ROOT` 환경 변수 설정 |
| `app/db/loader/phase3~6.py` | 각 Phase CSV/JSON 읽기 구현 완료 | 동일 |

### 병합 절차

```bash
# 1. backend/merge_all 기준으로 파이프라인 브랜치 생성
git checkout backend/merge_all
git checkout -b feat/pipeline-real-data

# 2. 파이프라인 출력 데이터를 PIPELINE_DATA_ROOT 경로에 배치
#    기본값: data/processed/
#    - data/processed/phase2/stationarity_results.csv
#    - data/processed/phase3/cointegration_results.csv
#    - data/processed/phase4/{commodity}_{segment}_model.json 등
#    - data/processed/phase5/granger_results.csv
#    - data/processed/phase6/{commodity}_{segment}_breakpoints.json

# 3. batch.py의 _run_phase() 스텁을 runner.py 실 호출로 교체
#    app/services/batch.py 내 _run_phase() 함수 참조

# 4. 마이그레이션 적용 및 시드 데이터 확인
alembic upgrade head

# 5. 수동 배치 트리거로 전체 파이프라인 검증
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger

# 6. pipeline_runs 테이블에서 status='completed' 확인 후 PR 생성
#    target: backend/merge_all
```

### 병합 후 확인 항목

- `pipeline_runs.status = 'completed'` (DB 직접 조회)
- `data_freshness` 테이블 갱신 확인
- Redis 캐시 무효화 후 `/api/v1/commodities/{id}/stream` 응답 확인
- `APP_ENV=production` 전환 후 서버 재기동 정상 여부

---

## 참조 문서

**버전 관리 단일 출처 (SoT)**: [`docs/docs_manifest.md`](docs/docs_manifest.md)

| 파일 | 설명 |
|---|---|
| `docs/api_spec_v5.md` | API 엔드포인트 명세 |
| `docs/db_schema_v5.md` | DB 스키마 명세 |
| `docs/exception_spec_v6.md` | 예외 코드 인덱스 (디버깅용) |
| `docs/exception_design_v3.md` | 예외 체이닝 설계 (심층 분석용) |
| `docs/pipeline_output_spec_v7.md` | 파이프라인 출력 명세 |
| `docs/feature_dev_list_v4.md` | feat/* 브랜치 기능 목록 |
