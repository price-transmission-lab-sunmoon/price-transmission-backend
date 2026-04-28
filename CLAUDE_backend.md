# CLAUDE.md — Backend

> **Claude Code 세션 자동 참조 컨텍스트 파일 (백엔드 repo 전용)**  
> 이 파일은 세션마다 반복 입력이 필요한 전역 제약·설계 결정·파라미터를 집중 관리한다.  
> 변경 시 단독 커밋: `[CLAUDE.md] Update {변경 내용}`

**최초 작성**: 2026-04-28  
**담당**: PM 최수안  
**참조 기준 문서**: `db_schema_v3`, `api_spec_v4`, `exception_spec_v4`, `web_plan_v6`, `pipeline_output_spec_v5`, `team_ai_collab_v6`

---

## 1. 프로젝트 요약

- **과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
- **이 repo의 역할**: FastAPI 백엔드 서버 — 파이프라인 repo의 분석 결과를 PostgreSQL에서 읽어 프론트엔드에 제공
- **데이터 흐름**: 파이프라인 repo (CSV 산출) → PostgreSQL 적재 → 이 repo (FastAPI) → 프론트엔드 repo
- **핵심 원칙**: 쓰기는 배치 파이프라인이 직접 DB에 적재. 모든 API 엔드포인트는 읽기 전용 (GET only)

---

## 2. 팀 역할

| 역할 | 담당 | 범위 |
|------|------|------|
| 백엔드 리드 | 샤킬라 | FastAPI·DB·API·배치·Redis — 이 repo 주담당 |
| PM | 최수안 | 명세 승인·게이트 체크 |
| 파이프라인 리드 | 예병성 | 파이프라인 repo. 이 repo의 DB 적재 인터페이스 제공 |
| 프론트엔드 리드 | 하대수 | 프론트엔드 repo. 이 repo의 API 소비자 |

---

## 3. 디렉토리 구조

```
price-transmission-backend/
├── CLAUDE.md                       ← 이 파일
├── README.md
├── docs/                           ← 참조 명세 사본 (읽기 전용)
│   ├── db_schema_vN.md
│   ├── api_spec_vN.md
│   ├── exception_spec_vN.md
│   ├── pipeline_output_spec_vN.md
│   └── results/                    ← 기능 구현 완료 후 작업 결과 명세
│       ├── DB-CONN.md
│       ├── API-STR.md
│       └── ...
├── app/
│   ├── main.py                     ← FastAPI 앱 진입점, 미들웨어, 라우터 등록
│   ├── config.py                   ← 환경 변수 로드 (Pydantic Settings)
│   ├── database.py                 ← SQLAlchemy 비동기 엔진·세션
│   ├── models/                     ← SQLAlchemy ORM 모델 (테이블 정의)
│   │   ├── commodity.py
│   │   ├── anomaly.py
│   │   ├── timeseries.py
│   │   └── ...
│   ├── schemas/                    ← Pydantic 요청·응답 스키마
│   │   ├── commodity.py
│   │   ├── anomaly.py
│   │   ├── timeseries.py
│   │   └── ...
│   ├── routers/                    ← API 엔드포인트 (라우터별 파일)
│   │   ├── commodities.py
│   │   ├── anomalies.py
│   │   ├── meta.py
│   │   └── ...
│   ├── services/                   ← 비즈니스 로직·DB 쿼리
│   │   ├── stream_service.py
│   │   ├── anomaly_service.py
│   │   └── ...
│   ├── cache/                      ← Redis 캐싱 레이어
│   │   └── redis_client.py
│   ├── batch/                      ← APScheduler 배치 작업
│   │   ├── scheduler.py
│   │   └── pipeline_runner.py
│   └── exceptions/                 ← 예외 클래스·핸들러
│       ├── errors.py               ← APIError, DBError 등 커스텀 예외
│       └── handlers.py             ← 글로벌 예외 핸들러
├── tests/
│   ├── conftest.py
│   └── ...
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 4. 기술 스택 (확정)

| 항목 | 선택 | 버전 |
|------|------|------|
| 언어 | Python | 3.11 |
| 웹 프레임워크 | FastAPI | 최신 |
| ORM | SQLAlchemy | 2.0 (비동기) |
| DB | PostgreSQL | 16 |
| 캐시 | Redis | 최신 |
| 배치 스케줄러 | APScheduler | 최신 |
| 컨테이너 | Docker + Docker Compose | — |
| 배포 | AWS 우선 (EC2 또는 ECS + RDS + ElastiCache) | — |
| CI/CD | GitHub Actions | — |

---

## 5. API 설계 원칙

1. **읽기 전용** — 전 엔드포인트 GET 방식. 쓰기는 배치 파이프라인이 직접 DB에 적재하며 API를 통하지 않는다.
2. **Base URL**: `/api/v1`
3. **응답 형식**: `application/json`
4. **날짜 형식**: `YYYY-MM` (Pydantic serializer가 DB `DATE` → `YYYY-MM` 변환)
5. **에러 형식**: `{"error": {"code": "...", "message": "...", "context": {...}}}`
6. **Redis 캐싱 대상**: 시계열 조회(`/stream`, `/raw-prices`, `/stat-series`) — Redis TTL 캐싱. 정적 데이터(`/meta/*`, `/segments`, `/events`) — `ETag` 기반 조건부 캐싱.
7. **이벤트 오버레이 정책**: 이벤트 배경 음영은 `/events` 별도 엔드포인트. 시계열 응답에 이벤트 데이터 포함 금지.
8. **응답 envelope**: 시계열 응답에 항상 `actual_from`/`actual_to`/`total_points` 포함.

---

## 6. 엔드포인트 목록

| 그룹 | 메서드 | 경로 | 설명 |
|------|--------|------|------|
| 참조 | GET | `/commodities` | 품목 목록 + 메타 정보 |
| 참조 | GET | `/commodities/{commodity_id}` | 단일 품목 상세 |
| 참조 | GET | `/segments` | 분석 구간 정의 목록 |
| 참조 | GET | `/events` | 외부 충격 이벤트 목록 |
| 참조 | GET | `/freshness` | 데이터 기준 시점 및 다음 갱신 예정일 |
| 요약 | GET | `/anomalies/summary` | 이달의 이상 요약 배너 |
| 시각화 | GET | `/commodities/{commodity_id}/stream` | 스트림 그래프 시계열 + 이상 노드 |
| 시각화 | GET | `/commodities/{commodity_id}/stream/minimap` | 미니맵 전용 (전체 기간 압축) |
| 시각화 | GET | `/commodities/{commodity_id}/scatter` | 전달 구조 산점도 |
| 시각화 | GET | `/commodities/{commodity_id}/raw-prices` | 원시 시계열 (2020=100 지수 포함) |
| 시각화 | GET | `/commodities/{commodity_id}/raw-prices/minimap` | 원시 시계열 미니맵 |
| 패널 | GET | `/anomalies/{anomaly_id}/detail` | 분석 수치 패널 전체 |
| 패널 | GET | `/anomalies/{anomaly_id}/stat-series` | 지표별 인라인 시계열 |
| 패널 | GET | `/anomalies/{anomaly_id}/stat-snapshot` | 비시계열 지표 스냅샷 |
| 패널 | GET | `/anomalies/{anomaly_id}/irf` | IRF 차트 데이터 |
| 패널 | GET | `/anomalies/{anomaly_id}/ml-map` | ML 결과맵 2D 투영 데이터 |
| 방법론 | GET | `/meta/pipeline` | 파이프라인 플로우 데이터 (정적) |
| 방법론 | GET | `/meta/analysis-params` | 파이프라인 파라미터 기준값 (정적) |

---

## 7. DB 테이블 목록

| 그룹 | 테이블명 | 역할 |
|------|----------|------|
| 참조 | `commodities` | 품목 메타 정보 |
| 참조 | `segments` | 분석 구간 정의 |
| 참조 | `external_events` | 외부 충격 이벤트 목록 |
| 원시 가격 | `raw_prices` | 원시 시계열 (원본값 + 2020=100 지수) |
| 계량 | `stationarity_results` | Phase 2 ADF+KPSS 검정 결과 |
| 계량 | `cointegration_results` | Phase 3 Johansen 공적분 검정 결과 |
| 계량 | `model_params` | Phase 4 VAR/VECM 추정 파라미터 |
| 계량 | `irf_data` | Phase 4 IRF 곡선 데이터 |
| 계량 | `baselines` | Phase 4 기준선 (정상 시차·전이탄력성·warmup_end) |
| 계량 | `granger_results` | Phase 5 Granger 인과 검정 결과 |
| 계량 | `breakpoints` | Phase 6 구조 변화 시점 |
| 계량 | `subperiods` | Phase 6 하위 기간 분할 정보 |
| 탐지 | `stat_timeseries` | Phase 7 지표별 전체 시계열 |
| 탐지 | `anomaly_results` | Phase 7+7-ML 이상 탐지 결과 + 신뢰도 등급 **(탐지 이벤트만)** |
| 탐지 | `asymmetry_results` | Phase 7 패턴 2 비대칭 검정 결과 |
| ML | `ml_scores` | Phase 7-ML 모델별 이상 점수 |
| ML | `ml_projections` | Phase 7-ML ML 결과맵 2D 투영 데이터 |
| 배치 | `pipeline_runs` | 월별 배치 실행 이력 |
| 배치 | `data_freshness` | 데이터 기준 시점 및 다음 갱신 예정일 |

> ⚠️ `anomaly_results`는 탐지 이벤트(이상 판정된 행)만 저장. 정상 월은 저장하지 않는다 (D-02).

---

## 8. 월 식별자 변환 규칙

| 계층 | 형식 | 예시 |
|------|------|------|
| 파이프라인 (Python) | `DatetimeIndex` (Month Start) | `2022-03-01` (Timestamp) |
| DB (PostgreSQL) | `DATE` YYYY-MM-01 고정 | `'2022-03-01'` |
| **API (이 repo)** | `YYYY-MM` 문자열 (Pydantic serializer) | `"2022-03"` |
| 프론트엔드 (TypeScript) | `string` YYYY-MM | `"2022-03"` |

**구현 규칙**:
- Pydantic 필드 타입: `str` + `field_validator`로 `YYYY-MM` 형식 강제
- DB→API 변환: `strftime("%Y-%m")`
- DB `period` 컬럼 적재 시 `period.day == 1` 검증 필수 (D-11)
- 타임스탬프(`last_updated` 등): ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)

---

## 9. 시계열 공통 쿼리 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|:----:|--------|------|
| `from` | `YYYY-MM` | — | 품목별 `analysis_start` | 조회 시작 월 (inclusive) |
| `to` | `YYYY-MM` | — | 최신 데이터 기준 월 | 조회 종료 월 (inclusive) |
| `granularity` | string | — | `"monthly"` | `"monthly"` \| `"quarterly"` \| `"yearly"` |

**granularity 집계 규칙**:
- `monthly`: 원본값 그대로, 1개월 = 1포인트
- `quarterly`: 3개월 평균 → 1포인트, 분기 마지막 월 기준
- `yearly`: 12개월 평균 → 1포인트, 연도 12월 기준
- granularity 무관하게 **이상 노드는 항상 원본 월 단위로 반환**

**시계열 응답 공통 envelope**:
```json
{
  "requested_from": "YYYY-MM",
  "requested_to":   "YYYY-MM",
  "actual_from":    "YYYY-MM",
  "actual_to":      "YYYY-MM",
  "granularity":    "monthly",
  "total_points":   36
}
```

---

## 10. 품목 분류 (파이프라인 repo와 공유)

### 3구간 품목 — A-B-D′ (7종)

`commodity_id`: `wheat`, `corn`, `soybean`, `palm_oil`, `sugar`, `coffee`, `beef`  
`has_wholesale: false`, `route_type: "3seg"`, `segments: ["A", "B", "D_prime"]`

### 4구간 품목 — A-B-C-D (3종)

`commodity_id`: `peanut`, `banana`, `orange`  
`has_wholesale: true`, `route_type: "4seg"`, `segments: ["A", "B", "C", "D"]`

**구간 유효성 검사**: 품목에 없는 구간 요청 시 `API-SEG-001` (400 `INVALID_SEGMENT`) 반환.

---

## 11. 신뢰도 등급 API 표현

| 등급 | DB/API 값 | 의미 |
|------|-----------|------|
| 고신뢰 | `"high"` | 통계 + ML 동시 확인 |
| 중신뢰 | `"medium"` | 통계 확인 + ML 미탐지 |
| 참고 | `"reference"` | ML 탐지 + 통계 미탐지 |

---

## 12. 예외 코드 (이 repo 담당 도메인)

### DB 도메인 (DB-*)

| 코드 | 원인 | 처리 방침 |
|------|------|-----------|
| `DB-CONN-001` | PostgreSQL 연결 실패 | FATAL |
| `DB-CONN-002` | 커넥션 풀 고갈 | RETRY 3회 |
| `DB-TX-001` | Phase 적재 중 트랜잭션 실패 | 해당 Phase 롤백 |
| `DB-UNIQ-001~003` | UNIQUE 위반 (raw_prices, anomaly_results, stat_timeseries) | UPSERT |
| `DB-FK-001~002` | commodity_id / segment_id 미존재 | FATAL |
| `DB-TYPE-001` | `period`가 월초(01일)가 아님 | FATAL |
| `DB-NN-001~002` | NOT NULL 위반 (confidence_grade, primary_pattern) | FATAL |
| `DB-CACHE-001` | Redis 연결 실패 | WARN (DB 직접 조회) |
| `DB-CACHE-002` | 캐시 직렬화/역직렬화 실패 | WARN (캐시 skip) |

### API 도메인 (API-*)

| 코드 | HTTP | public_code | 원인 |
|------|------|-------------|------|
| `API-COM-001` | 404 | `COMMODITY_NOT_FOUND` | 품목 미존재 |
| `API-ANO-001` | 404 | `ANOMALY_NOT_FOUND` | anomaly_id 미존재 |
| `API-STR-001` | 404 | `WARMUP_PERIOD_ONLY` | 전체 범위가 warmup 내 |
| `API-STR-002` | 400 | `INVALID_DATE_RANGE` | `from > to` |
| `API-STR-004` | 400 | `INVALID_GRANULARITY` | 허용 외 granularity 값 |
| `API-SEG-001` | 400 | `INVALID_SEGMENT` | 품목에 없는 구간 요청 |
| `API-LAY-002` | 400 | `WHOLESALE_NOT_AVAILABLE` | 3구간 품목에 레이아웃 4 요청 |
| `API-INT-001` | 500 | `INTERNAL_ERROR` | 내부 미매핑 예외 |
| `API-BATCH-001` | — | WARN | 배치 실행 중 예외 (서버 유지) |

### 파싱 도메인 (PARSE-*) — DB→API 경계

| 코드 | 원인 | 처리 방침 |
|------|------|-----------|
| `PARSE-DATE-001` | `DATE` → `YYYY-MM` 변환 실패 | CLIENT_500 |
| `PARSE-NUM-001` | `NUMERIC` → `float` 오버플로우 | CLIENT_500 |
| `PARSE-ENUM-001` | DB 열거형 값이 Pydantic Enum 외 | CLIENT_500 |
| `PARSE-REDIS-001` | Redis JSON 역직렬화 실패 | WARN (캐시 skip) |

> ⚠️ 신규 예외 상황은 `(proposed)` 표식으로 PM에게 제안 후 `exception_spec_vN.md` 등록 확정 전까지 임의 코드 사용 금지.

**예외 사용 패턴**:
```python
raise APIError(
    code="API-COM-001",
    message="품목 미존재",
    context={"commodity_id": commodity_id},
    http_status=404,
    public_code="COMMODITY_NOT_FOUND",
) from e   # 반드시 from e — 생략 금지
```

---

## 13. 배치 스케줄러 원칙

- 월별 자동 실행 (APScheduler)
- 각 Phase 적재는 단일 트랜잭션으로 묶는다
- 실패 시 해당 Phase 전체 롤백, `pipeline_runs.status='failed'` 기록
- 다음 재실행은 마지막 `completed` 상태 Phase부터 재시작
- 배치 중복 실행 감지 시 `API-BATCH-002` WARN 후 skip

---

## 14. 필드명 드리프트 방지

파이프라인 CSV 컬럼명 ↔ DB 테이블 컬럼명 ↔ API JSON 키 이름은 동일 대상이면 동일한 이름을 사용한다.

기준 문서 체인: `pipeline_output_spec_vN.md` → `db_schema_vN.md` → `api_spec_vN.md`

코드 생성 시 명시:
```
"이 컬럼명은 pipeline_output_spec_vN.md §Phase 4의
transmission_rate와 동일한 이름을 사용해줘."
```

---

## 15. 절대 금지사항

1. **쓰기 API 생성 금지**: 파이프라인 외부에서 DB에 데이터를 직접 쓰는 엔드포인트(POST/PUT/DELETE) 생성 금지. 배치 적재는 파이프라인 레이어만 수행
2. **미등록 예외 코드 생성 금지**: `exception_spec_vN.md`에 없는 에러 코드 임의 생성 금지. 신규 상황은 `(proposed)` 표식으로 제안 후 PM 리뷰 확정
3. **명세 없는 코딩 금지**: Feature 명세 PM 승인 전 `feat/` 브랜치 생성 및 코드 생성 금지
4. **이벤트 데이터 시계열 응답 포함 금지**: 이벤트 오버레이는 `/events` 엔드포인트 분리. 시계열 응답에 이벤트 필드 포함 금지
5. **DB 월 기준일 미검증 코드 생성 금지**: `period` 컬럼 적재 시 `period.day == 1` 검증 누락 금지
6. **`from None` 예외 체인 금지**: 예외 발생 시 반드시 `raise X from e` 사용

---

## 16. Git 커밋 컨벤션

형식: `[{영역}] {동사} {대상}`

| 영역 예시 | 용도 |
|-----------|------|
| `[API]` | 엔드포인트 추가·수정 |
| `[DB]` | ORM 모델·적재 로직 |
| `[Batch]` | APScheduler 배치 작업 |
| `[Redis]` | 캐싱 레이어 |
| `[Schema]` | Pydantic 스키마 |
| `[CLAUDE.md]` | 이 파일 수정 |

예시:
```
[API] Add /commodities/{id}/stream endpoint
[DB] Add anomaly_results upsert with DB-UNIQ-002 handling
[Batch] Add monthly pipeline_runs status tracking
[Redis] Add TTL cache for stream timeseries
[CLAUDE.md] Update directory structure after frame merge
```

**CLAUDE.md 수정은 반드시 단독 커밋.**

---

## 17. 세션 간 컨텍스트 승계 포맷

새 세션 시작 시 아래 포맷으로 제공:

```markdown
## 직전 세션 요약
- 완료한 작업: [예: /stream 엔드포인트 구현 완료]
- 확정된 함수명·변수명: [예: get_stream_timeseries(), commodity_id]
- 다음 작업: [예: /anomalies/{id}/detail 엔드포인트 구현]
- 미결 항목: [예: Redis TTL 값 확정 필요]
```

세션 15~20회 초과 시 정렬 프롬프트:
```
"지금까지 이 세션에서 확정한 함수명·스키마 구조를 요약해줘.
CLAUDE.md의 내용과 달라진 부분이 있으면 함께 알려줘."
```

---

## 18. 참조 문서 경로

| 문서 | 경로 |
|------|------|
| DB 스키마 | `docs/db_schema_vN.md` |
| API 명세 | `docs/api_spec_vN.md` |
| 예외처리 명세 | `docs/exception_spec_vN.md` |
| 파이프라인 출력 명세 | `docs/pipeline_output_spec_vN.md` |
| 웹 명세서 | `docs/web_plan_vN.md` |

> `vN`은 현재 최신 버전 번호로 교체한다.

---

*이 파일은 `docs/team_ai_collab_vN.md §3.1` 운용 원칙에 따라 관리된다. 디렉토리 구조·API 설계·예외 코드가 변경되면 CLAUDE.md를 즉시 갱신하고 단독 커밋한다.*
