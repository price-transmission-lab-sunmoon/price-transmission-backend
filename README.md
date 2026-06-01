# price-transmission-backend

계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지 — FastAPI 백엔드

---

## 빠른 시작 — 새 컴퓨터에서 실행 (Docker)

**Docker Desktop만 설치**되어 있으면 아래 순서로 app·PostgreSQL·Redis가 함께 뜨고,
적재 완료된 DB 스냅샷(`db/snapshot.sql.gz`)이 **최초 기동 시 자동 복원**된다.
Python 설치·`pip install`·`alembic`·데이터 적재 모두 **불필요**하다.

### 전체 순서

```bash
# 1. clone
git clone <repo-url>
cd price-transmission-backend

# 2. env 설정
cp .env.docker.example .env        # Windows PowerShell: copy .env.docker.example .env

# 3. 실행  ← 이 한 줄
docker compose up --build          # 포그라운드(로그 보임). 백그라운드면 끝에 -d
```

### 확인

```bash
curl http://localhost:8001/api/v1/meta/config      # → db_status:"ok", redis_status:"ok"
curl http://localhost:8001/api/v1/commodities       # → 품목 10개 (데이터 복원 확인)
```

또는 브라우저에서 Swagger UI: `http://localhost:8001/docs`

### 주의

- **`.env`는 그대로 사용** — `.env.docker.example`의 호스트는 이미 compose 서비스명(`db`/`redis`)이다. `localhost`로 바꾸지 말 것.
- **첫 실행만 `--build`** 필요(이미지 빌드 ~1분). 2회차부터는 `docker compose up -d`.
- 중지: `docker compose down`(데이터 유지) · `docker compose down -v`(DB 볼륨까지 삭제 → 다음 `up`에서 스냅샷 재복원).

### 구성

| 파일 | 역할 |
|---|---|
| `Dockerfile` | 서빙 전용 app 이미지 (python:3.11.9-slim, `app/`+`alembic/`만 — `data/`·`pipeline/` 미포함) |
| `docker-compose.yml` | `db`(postgres:16) + `redis`(redis:7) + `app`. healthcheck로 기동 순서 보장 |
| `db/snapshot.sql.gz` | 적재 완료 DB 전체 덤프(스키마+데이터+alembic_version). postgres `initdb`가 자동 복원 |
| `.env.docker.example` | compose용 `.env` 템플릿 (호스트 = `db`/`redis`) |
| `scripts/make-snapshot.ps1` / `.sh` | 현재 `pt_postgres`에서 스냅샷 재생성 |

### 데이터 갱신 흐름

컨테이너 이미지에는 `pipeline/`·`data/`가 없으므로 **컨테이너 내 배치 트리거(`/admin/batch/trigger`)·파이프라인 재계산은 동작하지 않는다.**
데이터를 갱신하려면 (1) 아래 "사전 준비(네이티브 개발)" 환경에서 파이프라인 실행 + DB 적재 → (2) 스냅샷 재생성:

```bash
# pt_postgres 기동 상태에서
powershell -ExecutionPolicy Bypass -File scripts\make-snapshot.ps1   # Windows
sh scripts/make-snapshot.sh                                          # Mac/Linux
# → db/snapshot.sql.gz 갱신. 새 PC에서 docker compose down -v 후 up --build 시 새 스냅샷 복원
```

> 스냅샷이 50MB를 넘으면 git 직접 커밋 대신 git-lfs 또는 S3 다운로드로 전환 권장. (현재 ~1MB)

AWS 배포 검토는 [`docs/DEPLOY_AWS.md`](docs/DEPLOY_AWS.md) 참조.

---

## 브랜치 구조

| 브랜치 | 설명 |
|---|---|
| `main` | 안정 브랜치 |
| `backend/refactoring` | 중복 로직 단일 출처 통합 리팩토링 (현재 작업 브랜치) |
| `backend/merge_all` | 백엔드 전체 기능 통합 브랜치 |
| `feat/be-*` | 기능별 개발 브랜치 (병합 완료) |

---

## 사전 준비 (네이티브 개발)

> 아래는 코드를 직접 고치며 개발할 때의 절차다. 단순 실행만 필요하면 위 "Docker로 즉시 실행"을 쓴다.

- Python 3.11.9
- PostgreSQL 16 (로컬 또는 Docker)
- Redis 7+ (로컬 또는 Docker)
- Docker Desktop (아래 컨테이너 기동 방식 사용 시)

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경 변수 설정 (.env 파일 생성)
cp .env.example .env
# .env 에서 필수 항목 설정 (아래 변수 목록 참조)
```

### PostgreSQL · Redis 기동 (Docker)

이 레포에는 `docker-compose.yml`이 없으므로, `.env` 기본값에 맞춰 컨테이너를 직접 생성한다.

```bash
# 최초 1회 — 컨테이너 생성 (.env 의 DATABASE_URL / REDIS_URL 기본값과 일치)
docker run -d --name pt_postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=price_transmission \
  -p 5432:5432 postgres:16

docker run -d --name pt_redis -p 6379:6379 redis:7
```

> 위 설정은 `DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/price_transmission`,
> `REDIS_URL=redis://localhost:6379/0` 과 일치한다. `.env` 를 바꾸면 컨테이너 옵션도 함께 맞춘다.

```bash
# 2회차부터 — 기존 컨테이너 재기동 (서버 켜기 전 항상 먼저 실행)
docker start pt_postgres pt_redis

# 상태 확인 (Postgres 가 'accepting connections' 이면 준비 완료)
docker ps
docker exec pt_postgres pg_isready -U postgres
```

> ⚠️ 컨테이너를 띄우지 않으면 `APP_ENV=development` 기본값 때문에 서버는 기동되지만
> PostgreSQL `WinError 1225` · Redis 연결 거부 경고가 뜨고 **DB 조회 엔드포인트가 동작하지 않는다.**

### .env 전체 변수 목록

```dotenv
# 필수 (아래 값은 "사전 준비"의 Docker 컨테이너 설정과 일치)
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/price_transmission
REDIS_URL=redis://localhost:6379/0

# 선택 (기본값 있음)
APP_ENV=development          # development | production
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR
CORS_ALLOWED_ORIGINS=http://localhost:5173

# 파이프라인 데이터 경로
PIPELINE_DATA_ROOT=data/processed   # 파이프라인 CSV/JSON 출력 루트

# 배치 스케줄
BATCH_SCHEDULE_DAY=15        # 매월 몇 일 실행
BATCH_SCHEDULE_HOUR=3        # 실행 시각 (KST 기준)
BATCH_SCHEDULE_TZ=Asia/Seoul

# Redis 캐싱
REDIS_TTL=3600
REDIS_CACHE_PREFIX=pricelens

# Phase 0 데이터 수집 API 키 (데이터 수집 시 필요)
ECOS_API_KEY=                # 한국은행 ECOS Open API
EXIM_API_KEY=                # 관세청 수출입 무역통계
KAMIS_CERT_KEY=              # KAMIS 농산물유통정보
KAMIS_CERT_ID=
```

> **`APP_ENV=development`** 시: PostgreSQL·Redis 연결 실패해도 서버 기동 (WARN 로그만 출력).  
> **`APP_ENV=production`** 시: 연결 실패 시 `CFG-CORE-001` FATAL, 기동 중단.

---

## 서버 실행

기본 포트는 **8001** 고정이다.

```bash
# 1. DB/Redis 컨테이너 기동 (위 "사전 준비" 참조)
docker start pt_postgres pt_redis

# 2. DB 마이그레이션 적용 (스키마 최신화 — 최초 1회 또는 마이그레이션 추가 시)
alembic upgrade head

# 3a. 개발 서버 (hot-reload)
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 3b. 프로덕션
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

기동 로그에 `PostgreSQL 연결 확인` 이 보이면 정상이다.
(`PostgreSQL 연결 실패 … development 모드이므로 기동 계속` 이 뜨면 1번 컨테이너 기동을 확인한다.)

서버 기동 후 확인:
- Swagger UI: `http://localhost:8001/docs`
- 헬스체크: `GET http://localhost:8001/api/v1/meta/config`

---

## 파이프라인 실행

월별 배치(`/api/v1/admin/batch/trigger`)는 내부적으로 Phase 0~6을 순서대로 실행합니다.  
각 Phase를 단독으로 실행하려면 아래 명령어를 사용합니다.

### Phase 0 — 데이터 수집 및 전처리

원시 데이터를 수집하고 `data/processed/merged/` 에 통합 CSV를 생성합니다.  
API 키(ECOS, EXIM, KAMIS)가 `.env` 에 설정되어 있어야 합니다.

```bash
python -m pipeline.preprocessing.run_phase0
```

**출력 경로:**

```
data/processed/
├── worldbank_prices_krw.csv          # 원화 환산 국제가
├── common_periods.csv                # 공통 분석 기간
├── missing_value_report.csv          # 결측치 리포트
├── product_config.json               # 품목별 분석 설정
└── merged/
    ├── all_commodities.csv           # 전체 통합 데이터셋
    └── {commodity_id}.csv            # 품목별 개별 파일
```

### Phase 1 — 계절 조정 (STL)

```bash
python -m pipeline.preprocessing.phase1_seasonal_adjustment
```

**출력 경로:**

```
data/processed/phase1/
├── seasonal_adjusted/{cid}_sa.csv    # 계절 조정 시계열 (수준)
├── changes/{cid}_changes.csv         # 전월 대비 변화율 (%)
├── stl_components/{cid}_stl.csv      # STL 분해 성분
└── phase1_summary.csv
```

### Phase 2 — 정상성 검정 (ADF + KPSS)

```bash
python -m pipeline.preprocessing.phase2_stationarity_test
```

**출력 경로:**

```
data/processed/phase2/
├── stationarity_results.csv          # 전체 검정 결과
└── integration_orders.json           # 품목·컬럼별 적분 차수 (Phase 3 입력)
```

### Phase 3 — 공적분 검정 (Johansen)

```bash
python -m pipeline.preprocessing.phase3_cointegration_test
```

**출력 경로:**

```
data/processed/phase3/
├── cointegration_results.csv         # 전체 검정 결과
└── model_routing.json                # 구간별 모형 선택 (VAR/VECM)
```

### Phase 4 — 모형 추정 (VAR/VECM + IRF)

```bash
python -m pipeline.preprocessing.phase4_model_estimation
```

**출력 경로:**

```
data/processed/phase4/
├── model_params/{cid}_{seg}_model.json
├── irf/{cid}_{seg}_irf.csv
├── baseline/{cid}_{seg}_baseline.json
├── ect/{cid}_{seg}_ect.csv
└── phase4_summary.csv
```

### Phase 5 — Granger 인과 방향 확정

```bash
python -m pipeline.preprocessing.phase5_granger_causality
```

**출력 경로:**

```
data/processed/phase5/
├── granger_results.csv               # 검정 결과 (3품목 × 2방향)
└── granger_direction.json            # 확정 방향
```

### Phase 6 — 구조 변화 탐지 (Bai-Perron)

```bash
python -m pipeline.preprocessing.phase6_structural_breaks
```

**출력 경로:**

```
data/processed/phase6/
├── breakpoints/{cid}_{seg}_breakpoints.json
├── chow_results/{cid}_{seg}_chow.csv
├── subperiod_models/{cid}_{seg}_subperiod_{n}_model.json
└── phase6_summary.csv
```

### Phase 7 — 이상 패턴 탐지 (통계)

```bash
python -m pipeline.preprocessing.Phase7.phase7_pattern1
python -m pipeline.preprocessing.Phase7.phase7_pattern2
python -m pipeline.preprocessing.Phase7.phase7_pattern3
python -m pipeline.preprocessing.Phase7.phase7_integrate
```

**출력 경로:**

```
data/processed/phase7/
├── pattern1/{cid}_{seg}_pattern1.csv
├── pattern2/{cid}_{seg}_pattern2_zscore.csv
├── pattern2/{cid}_{seg}_pattern2_asymmetry.csv
├── pattern3/{cid}_{seg}_pattern3.csv
├── stat_timeseries/{cid}_{seg}_stat_timeseries.csv
└── phase7_summary.csv
```

### Phase 7-ML — ML 보조 교차검증

```bash
python -m pipeline.preprocessing.Phase7.phase7_ml_run
```

**출력 경로:**

```
data/processed/phase7_ml/
├── features/{cid}_{seg}_features.csv
├── predictions/{cid}_{seg}_ml_predictions.csv
├── cross_validation/{cid}_{seg}_cross_val.csv
├── confidence_grades/{cid}_{seg}_grades.csv
├── models/{YYYYMMDD_HHMM}/...pkl + run_log_*.json
└── phase7_ml_summary.csv
```

### Phase 2~7-ml DB 적재 (배치 수동 트리거)

파이프라인 계산이 완료된 후 DB에 적재하려면:

```bash
# 서버 실행 후 수동 배치 트리거
curl -X POST http://localhost:8001/api/v1/admin/batch/trigger

# 또는 전체 파이프라인 계산 + 적재 일괄 실행
curl -X POST http://localhost:8001/api/v1/admin/batch/trigger
```

### 전체 파이프라인 순차 실행

```bash
# Phase 0: 데이터 수집
python -m pipeline.preprocessing.run_phase0

# Phase 1: 계절 조정
python -m pipeline.preprocessing.phase1_seasonal_adjustment

# Phase 2: 정상성 검정
python -m pipeline.preprocessing.phase2_stationarity_test

# Phase 3: 공적분 검정
python -m pipeline.preprocessing.phase3_cointegration_test

# Phase 4: 모형 추정
python -m pipeline.preprocessing.phase4_model_estimation

# Phase 5: Granger 인과
python -m pipeline.preprocessing.phase5_granger_causality

# Phase 6: 구조 변화
python -m pipeline.preprocessing.phase6_structural_breaks

# Phase 7: 이상 패턴 탐지 (통계)
python -m pipeline.preprocessing.Phase7.phase7_pattern1
python -m pipeline.preprocessing.Phase7.phase7_pattern2
python -m pipeline.preprocessing.Phase7.phase7_pattern3
python -m pipeline.preprocessing.Phase7.phase7_integrate

# Phase 7-ML: ML 보조 교차검증
python -m pipeline.preprocessing.Phase7.phase7_ml_run

# DB 적재 (서버 실행 상태에서)
curl -X POST http://localhost:8001/api/v1/admin/batch/trigger
```

---

## 주요 명령

| 목적 | 명령 |
|---|---|
| DB/Redis 컨테이너 기동 | `docker start pt_postgres pt_redis` |
| 개발 서버 | `uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload` |
| DB 마이그레이션 적용 | `alembic upgrade head` |
| 마이그레이션 1단계 롤백 | `alembic downgrade -1` |
| 테스트 실행 | `pytest` |
| 특정 테스트 파일 | `pytest tests/test_api_reference.py -v` |
| 린트 | `ruff check .` |
| 포맷 | `ruff format .` |
| 수동 배치 트리거 | `curl -X POST http://localhost:8001/api/v1/admin/batch/trigger` |
| pipeline_runs 상태 확인 | `docker exec pt_postgres psql -U postgres -d price_transmission -c "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 5;"` |

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
│   └── batch.py             APScheduler 월별 배치 + 파이프라인 실행
└── cache/
    └── redis.py             Redis 클라이언트 + cache_get/set/delete 헬퍼

pipeline/                    파이프라인 계산 코드 (price-transmission 리포 통합)
├── __init__.py
├── preprocessing/           Phase 0~6 계산 스크립트
│   ├── run_phase0.py        데이터 수집 통합 실행기
│   ├── step1~5_*.py         Phase 0 세부 단계 (수집·전처리)
│   ├── phase1~6_*.py        Phase 1~6 계량경제 분석
│   └── Phase7/              Phase 7 이상 탐지·ML (phase7-stat 완료 후 연결 예정)
├── collectors/              원시 데이터 수집기 (ECOS, KAMIS, 세계은행 등)
└── config/
    ├── settings.py          파이프라인 파라미터 설정
    └── commodity_mapping.json

data/
├── raw/                     원시 데이터 (수집기 출력, git 제외)
└── processed/               파이프라인 중간·최종 산출물 (git 제외)
    ├── product_config.json
    ├── merged/
    ├── phase1/ ~ phase6/

alembic/                     DB 마이그레이션 (7개 revision)
tests/                       pytest 테스트 (DB·Redis 없이 실행 가능)
docs/                        명세 문서 (버전 관리: docs_manifest_v3.md)
```

---

## 배치 실행 흐름

월별 배치(또는 수동 트리거)는 다음 순서로 실행됩니다:

```
Phase 0 → Phase 1 → Phase 2 (+DB 적재) → Phase 3 (+DB 적재)
→ Phase 4 (+DB 적재) → Phase 5 (+DB 적재) → Phase 6 (+DB 적재)
→ Phase 7 (pattern1/2/3 + integrate, +DB 적재)
→ Phase 7-ml (phase7_ml_run, +DB 적재)
→ data_freshness 갱신 → Redis 캐시 무효화
```

Phase 2~7-ml 모두 계산 완료 직후 DB 적재가 이루어집니다.  

- Phase 7 적재 테이블: `stat_timeseries`, `anomaly_results`
- Phase 7-ml 적재 테이블: `ml_scores` (`if_percentile`/`lof_percentile`/`svm_percentile`은 segment 단위 백엔드 산출)
- ML 결과맵(`ml_projections`)은 별도 PR(③)에서 활성화 예정.

### 배치 완료 확인

```bash
# pipeline_runs 상태 확인 (pt_postgres 컨테이너 내부 psql 실행)
docker exec pt_postgres psql -U postgres -d price_transmission -c \
  "SELECT id, run_date, status, phases_run, finished_at FROM pipeline_runs ORDER BY id DESC LIMIT 5;"

# data_freshness 갱신 확인
docker exec pt_postgres psql -U postgres -d price_transmission -c \
  "SELECT data_up_to, next_run_date, last_updated FROM data_freshness;"

# Redis 캐시 무효화 후 응답 확인
curl http://localhost:8001/api/v1/commodities/wheat/stream
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

## 참조 문서

**버전 관리 단일 출처 (SoT)**: [`docs/docs_manifest_v3.md`](docs/docs_manifest_v3.md)

| 파일 | 설명 |
|---|---|
| `docs/api_spec_v6.md` | API 엔드포인트 명세 |
| `docs/db_schema_v6.md` | DB 스키마 명세 |
| `docs/exception_spec_v6.md` | 예외 코드 인덱스 (디버깅용) |
| `docs/exception_design_v3.md` | 예외 체이닝 설계 (심층 분석용) |
| `docs/pipeline_output_spec_v9.md` | 파이프라인 출력 명세 |
| `docs/feature_dev_list_v5.md` | feat/* 브랜치 기능 목록 |
