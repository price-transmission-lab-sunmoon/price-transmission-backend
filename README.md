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

`docs/` 폴더 내 명세 문서 참조.

| 파일 | 설명 |
|---|---|
| `frame_spec_backend_v2.md` | 백엔드 프레임 명세 |
| `api_spec_v4.md` | API 엔드포인트 명세 |
| `db_schema_v3.md` | DB 스키마 명세 |
| `exception_spec_v4.md` | 예외 코드 인덱스 |
| `exception_design_v2.md` | 예외 처리 구현 가이드 |
| `pipeline_output_spec_v5.md` | 파이프라인 출력 명세 |
| `doc1_technical_pipeline_v9.md` | 파이프라인 기술 명세 |
| `doc2_pattern_definitions_v2.md` | 패턴 정의 |
| `doc3_research_proposal_v11.md` | 연구 제안서 |
| `web_plan_v6.md` | 웹 서비스 기획서 |
| `CLAUDE.md` | AI 코딩 어시스턴트 컨텍스트 |
