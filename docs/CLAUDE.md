# CLAUDE.md — price-transmission-backend

## 프로젝트 개요

계량경제학 모형과 머신러닝 기반 소비자 물가 이상 탐지 시스템의 FastAPI 백엔드.

## 참조 문서 (docs/ 폴더)

> **버전 해석 SoT**: [`docs_manifest.md`](docs_manifest.md) — 아래 모든 `_vN` 표기의 실제 버전·파일명은 본 manifest의 §1 표에서 해석된다. 상위 명세 갱신 시 manifest 한 파일만 고치면 전 문서 참조가 갱신된다. **작업 전 필수**: manifest §1 표의 파일이 `docs/`에 모두 존재하는지 확인 (§2.2 파일 부재 방지 규칙).

- `doc1_technical_pipeline_vN.md` — 파이프라인 Phase 0~9 기술 명세
- `doc2_pattern_definitions_vN.md` — 패턴 정의
- `doc3_research_proposal_vN.md` — 연구 제안서
- `web_plan_vN.md` — 웹 서비스 기획서
- `pipeline_output_spec_vN.md` — 파이프라인 출력 명세
- `db_schema_vN.md` — DB 스키마 명세 (단일 권위 출처)
- `api_spec_vN.md` — API 명세 (단일 권위 출처)
- `exception_spec_vN.md` — 예외 코드 인덱스 (반복 조회용)
- `exception_design_vN.md` — 예외 체이닝 설계 (심층 분석용)
- `frame_spec_backend_vN.md` — 백엔드 Frame 명세
- `sprint_plan_vN.md` — 스프린트 계획 _(외부 입고 대기)_
- `feature_dev_list_vN.md` — feat/* 브랜치 기능 개발 목록

## 기술 스택

- Python 3.11.9
- FastAPI 0.111.0 + Pydantic v2
- SQLAlchemy 2.0 비동기 (asyncpg)
- Alembic 1.13.1
- Redis 5.0.4

## 코딩 규칙

### 필드명
- Pydantic 필드명은 DB 컬럼명과 동일한 `snake_case` 유지
- `alias_generator` (camelCase 변환) **절대 금지**
- `populate_by_name=True` 허용

### 날짜 직렬화
- `period` (DATE 월) → `YYYY-MM` 문자열 (Pydantic serializer)
- `start_date` / `end_date` → `YYYY-MM-DD`
- `created_at` / `last_updated` → ISO 8601 UTC `Z` 접미사

### Literal 타입
고정 enum 값은 반드시 `typing.Literal[...]` 사용:
- `cluster`: `Literal['grain','oil_sugar','tropical','livestock','independent']`
- `route_type`: `Literal['3seg','4seg']`
- `confidence_grade`: `Literal['high','medium','reference']`
- `primary_pattern`: `Literal['pattern1','pattern2','pattern3']`
- `model_type`: `Literal['VAR','VECM']`
- `granularity`: `Literal['monthly','quarterly','yearly']`
- `ect_type`: `Literal['ECT','log_spread'] | None`
- `pipeline_runs.status`: `Literal['running','completed','failed']`

### 에러 응답
모든 에러는 `{"error": {"code": "...", "message": "...", "context": {...}}}` envelope 사용.
외부 코드는 `api_spec_vN.md §에러 코드 정의` 13종 + `INTERNAL_ERROR` 1종만 사용.

### ORM → Pydantic 변환
- endpoint에서 ORM 모델 직접 반환 **금지**
- service 함수에서 명시적 변환 후 DTO 반환
- `from_attributes=True` 허용, relationship lazy load는 await로 해소 후

### 환경 변수
- 시크릿/패스워드 하드코딩 **금지**
- `VITE_*` 변수 백엔드 설정에 포함 **금지**

### Alembic
- Frame 단계: autogenerate **금지**, 수동 작성 2개 revision만
- 버전 파일: `0001_initial_frame_tables.py`, `0002_seed_reference_data.py`

## 디렉토리 구조 (Frame 단계)

```
app/
├── main.py
├── api/
│   ├── deps.py
│   └── v1/
│       ├── router.py
│       └── endpoints/
│           ├── commodities.py
│           ├── anomalies.py
│           └── meta.py
├── core/
│   ├── config.py
│   ├── exceptions.py
│   └── logging.py
├── db/
│   ├── base.py
│   ├── session.py
│   └── models/
│       ├── commodity.py
│       ├── anomaly.py
│       ├── timeseries.py
│       └── batch.py
├── schemas/
│   ├── error.py
│   ├── commodity.py
│   ├── anomaly.py
│   ├── timeseries.py
│   └── meta.py
├── cache/
│   └── redis.py
└── services/   (Frame 단계 빈 상태)
```

## feat 브랜치 계획

- `feat/be-api-reference` — /commodities, /segments, /events, /freshness 실 DB 연결
- `feat/be-api-timeseries` — /stream, /scatter, /raw-prices
- `feat/be-api-panel` — /anomalies/{id}/* 패널
- `feat/be-api-anomaly` — /anomalies/summary
- `feat/be-api-meta` — /meta/pipeline, /meta/analysis-params
- `feat/be-redis` — Redis 캐싱
- `feat/be-batch` — APScheduler 월 배치
- `feat/pipeline-phase2-3` — stationarity_results, cointegration_results ORM
- `feat/pipeline-phase4-5` — model_params, irf_data, baselines, granger_results ORM
- `feat/pipeline-phase6-7` — breakpoints, subperiods ORM
- `feat/pipeline-phase7-ml` — ml_scores, ml_projections ORM
