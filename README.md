# price-transmission-backend

계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지 — FastAPI 백엔드

## 브랜치 구조

- `main` — 안정 브랜치
- `frame/backend` — 골격 설정 (이 브랜치)
- `feat/*` — 기능별 개발 브랜치

## 사전 준비

- Python 3.11.9
- PostgreSQL 16
- Redis

```bash
cp .env.example .env
# .env 파일에서 DATABASE_URL, REDIS_URL 설정
pip install -r requirements.txt
```

## 실행 스크립트

| 스크립트 | 명령 | 용도 |
|---|---|---|
| `dev` | `uvicorn app.main:app --reload --port 8000` | 개발 서버 |
| `migrate` | `alembic upgrade head` | DB 마이그레이션 적용 |
| `migrate:rollback` | `alembic downgrade -1` | 1단계 롤백 |
| `test` | `pytest` | 전체 테스트 |
| `lint` | `ruff check .` | 린트 |
| `format` | `ruff format .` | 포맷 |
| `format:check` | `ruff format --check .` | 포맷 검증 |

## 디렉토리 구조

```
app/
├── main.py              FastAPI 진입점
├── api/v1/              라우터 + 엔드포인트
├── core/                설정, 예외, 로깅
├── db/                  ORM 모델, 세션
├── schemas/             Pydantic 응답 DTO
└── cache/               Redis 클라이언트
alembic/                 DB 마이그레이션
tests/                   테스트
docs/                    명세 문서
```

## API

Base URL: `/api/v1`

헬스체크: `GET /api/v1/meta/config`

Swagger UI: `http://localhost:8000/docs`

## 참조 문서

**버전 관리 단일 출처 (SoT)**: [`docs/docs_manifest.md`](docs/docs_manifest.md) — 모든 명세 문서의 **현재 최신 버전**과 **문서 간 참조 관계**를 이 파일에서 관리한다. 명세 문서 본문은 `abcd_vN.md` 표기만 사용하며, 실제 버전 해석은 manifest의 §1 표를 통해 이뤄진다.

**⚠️ 작업 안전 규칙**: manifest §1 표의 버전에 해당하는 파일이 실제로 `docs/`에 존재하지 않으면, **AI·사람 모두 해당 참조가 포함된 작업을 진행하지 않는다** (manifest §2.2).

현재 `docs/` 폴더의 명세 문서 (manifest §1에서 자동 추출):

| 파일 (vN 패턴) | 현재 파일 | 설명 |
|---|---|---|
| `docs_manifest.md` | `docs_manifest.md` | **버전·참조 맵 단일 출처 (SoT)** |
| `frame_spec_backend_vN.md` | `frame_spec_backend_v3.md` | 백엔드 프레임 명세 |
| `frame_spec_frontend_vN.md` | `frame_spec_frontend_v4.md` | 프론트 프레임 명세 |
| `api_spec_vN.md` | `api_spec_v5.md` | API 엔드포인트 명세 |
| `db_schema_vN.md` | `db_schema_v5.md` | DB 스키마 명세 |
| `exception_spec_vN.md` | `exception_spec_v5.md` | 예외 코드 인덱스 |
| `exception_design_vN.md` | `exception_design_v3.md` | 예외 처리 구현 가이드 |
| `pipeline_output_spec_vN.md` | `pipeline_output_spec_v7.md` | 파이프라인 출력 명세 |
| `doc1_technical_pipeline_vN.md` | `doc1_technical_pipeline_v10.md` | 파이프라인 기술 명세 |
| `doc2_pattern_definitions_vN.md` | `doc2_pattern_definitions_v2.md` | 패턴 정의 |
| `doc3_research_proposal_vN.md` | `doc3_research_proposal_v11.md` | 연구 제안서 |
| `web_plan_vN.md` | `web_plan_v6.md` | 웹 서비스 기획서 |
| `feature_dev_list_vN.md` | `feature_dev_list_v4.md` | feat/* 브랜치 기능 개발 목록 |
| `CLAUDE.md` | `CLAUDE.md` | AI 코딩 어시스턴트 컨텍스트 |

외부 입고 대기: `sprint_plan_vN.md`, `team_ai_collab_vN.md` (manifest §1.1 참조).
