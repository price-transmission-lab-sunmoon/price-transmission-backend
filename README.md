# price-transmission-backend

계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지 — FastAPI 백엔드

---

## 브랜치 구조

| 브랜치 | 설명 |
|---|---|
| `main` | 안정 브랜치 |
| `backend/merge_all` | 백엔드 전체 기능 통합 브랜치 (현재 최신) |
| `feat/be-*` | 기능별 개발 브랜치 (병합 완료) |

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
# .env 에서 필수 항목 설정 (아래 변수 목록 참조)
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

### Phase 2~6 DB 적재 (배치 수동 트리거)

파이프라인 계산이 완료된 후 DB에 적재하려면:

```bash
# 서버 실행 후 수동 배치 트리거
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger

# 또는 전체 파이프라인 계산 + 적재 일괄 실행
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger
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

# DB 적재 (서버 실행 상태에서)
curl -X POST http://localhost:8000/api/v1/admin/batch/trigger
```

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
| 수동 배치 트리거 | `curl -X POST http://localhost:8000/api/v1/admin/batch/trigger` |
| pipeline_runs 상태 확인 | `psql -c "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 5;"` |

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
docs/                        명세 문서 (버전 관리: docs_manifest.md)
```

---

## 배치 실행 흐름

월별 배치(또는 수동 트리거)는 다음 순서로 실행됩니다:

```
Phase 0 → Phase 1 → Phase 2 (+DB 적재) → Phase 3 (+DB 적재)
→ Phase 4 (+DB 적재) → Phase 5 (+DB 적재) → Phase 6 (+DB 적재)
→ Phase 7 (미구현, skip) → Phase 7-ml (미구현, skip)
→ data_freshness 갱신 → Redis 캐시 무효화
```

Phase 2~6은 계산 완료 직후 DB 적재가 이루어집니다.  
Phase 7, 7-ml은 `phase7-stat` 구현 완료 후 연결됩니다.

### 배치 완료 확인

```bash
# pipeline_runs 상태 확인
psql -U user -d price_transmission -c \
  "SELECT id, run_date, status, phases_run, finished_at FROM pipeline_runs ORDER BY id DESC LIMIT 5;"

# data_freshness 갱신 확인
psql -U user -d price_transmission -c \
  "SELECT data_up_to, next_run_date, last_updated FROM data_freshness;"

# Redis 캐시 무효화 후 응답 확인
curl http://localhost:8000/api/v1/commodities/wheat/stream
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

**버전 관리 단일 출처 (SoT)**: [`docs/docs_manifest.md`](docs/docs_manifest.md)

| 파일 | 설명 |
|---|---|
| `docs/api_spec_v5.md` | API 엔드포인트 명세 |
| `docs/db_schema_v5.md` | DB 스키마 명세 |
| `docs/exception_spec_v6.md` | 예외 코드 인덱스 (디버깅용) |
| `docs/exception_design_v3.md` | 예외 체이닝 설계 (심층 분석용) |
| `docs/pipeline_output_spec_v7.md` | 파이프라인 출력 명세 |
| `docs/feature_dev_list_v4.md` | feat/* 브랜치 기능 목록 |
