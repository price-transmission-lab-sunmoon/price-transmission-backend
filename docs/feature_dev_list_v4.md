# 기능 개발 리스트 v4

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: feat/* 브랜치 기능 개발 관리 (frame/* 머지 이후 적용)
**작성일**: 2026-04-27
**담당**: PM 최수안
**참조** (최신 버전 자동 참조 — `abcd_vN.md` 규칙): sprint_plan_vN.md, api_spec_vN.md, web_plan_vN.md, db_schema_vN.md
**변경 이력**:
- v2 -> v3 (2026-04-27) : 당시 pipeline_output_spec v5 에서 v6으로 버전 업.
- v3 -> v4 (2026-05-02) : 본문 정정. `reference_audit_report v1` §4 규칙에 따라 외부 참조 표기를 `abcd_vN.md`로 일괄 전환. 잔존 구버전 참조(당시 doc1 v9, db_schema v3) 전부 정정. 본 문서는 이제 `docs/docs_manifest.md`의 버전 해석기에 의해 자동 최신 참조된다.


> **운영 원칙**
> - Phase 0~6 파이프라인은 예병성 자체 주도로 개발 중이므로 이 문서에서 제외.
> - Phase 7·7-ML은 예병성이 초안을 작성하고 팀 4인 검토 후 확정.
> - 백엔드 전체: 샤킬라 리드 / 프론트엔드 전체: 하대수 리드.
> - feat/* 브랜치는 기능 명세 PM 승인 후 생성. frame/* dev 머지 전 생성 금지.
> - 스프린트 일정은 유동적. 착수 전 sprint_plan 최신 버전 확인 필수.

---

## 전체 브랜치 요약

| 브랜치 | 영역 | 리드 | 스프린트 | 선행 조건 |
|--------|------|------|----------|-----------|
| `feat/phase7-stat` | 파이프라인 | 예병성 (팀 검토) | S3 | Phase 6 완료 |
| `feat/phase7-ml` | 파이프라인 | 예병성 (팀 검토) | S4 | phase7-stat 완료 |
| `feat/be-api-reference` | 백엔드 | 샤킬라 | S2 | frame/backend 머지 |
| `feat/be-api-anomaly` | 백엔드 | 샤킬라 | S2~S3 | frame/backend 머지 |
| `feat/be-api-timeseries` | 백엔드 | 샤킬라 | S3 | phase7-stat 완료 |
| `feat/be-api-panel` | 백엔드 | 샤킬라 | S4 | phase7-ml 완료 |
| `feat/be-db-pipeline` | 백엔드 | 샤킬라 | S3 | frame/backend 머지 |
| `feat/be-batch` | 백엔드 | 샤킬라 | S4 | be-api-reference 완료 |
| `feat/be-redis` | 백엔드 | 샤킬라 | S5 | be-db-pipeline 완료 |
| `feat/fe-layout-filter` | 프론트엔드 | 하대수 | S3 | frame/frontend 머지 |
| `feat/fe-stream-chart` | 프론트엔드 | 하대수 | S3 | frame/frontend 머지 |
| `feat/fe-minimap` | 프론트엔드 | 하대수 | S3 | fe-stream-chart 완료 |
| `feat/fe-panel` | 프론트엔드 | 하대수 | S4 | fe-stream-chart 완료 |
| `feat/fe-scatter-chart` | 프론트엔드 | 하대수 | S4 | fe-panel 완료 |
| `feat/fe-raw-timeseries` | 프론트엔드 | 하대수 | S4 | fe-layout-filter 완료 |
| `feat/fe-methodology-tab` | 프론트엔드 | 하대수 | S5 | be-api-panel 완료 |
| `feat/fe-onboarding` | 프론트엔드 | 하대수 | S5 | fe-panel 완료 |
| `feat/fe-api-connect` | 프론트엔드 | 하대수 | S6 | 전 백엔드 feat 완료 |

---

## 파이프라인 (예병성 · 팀 4인 검토)

### feat/phase7-stat — 통계 기반 이상 탐지

| 항목 | 내용 |
|------|------|
| **리드** | 예병성 초안 → 팀 4인 검토 후 확정 |
| **브랜치** | `feat/phase7-stat` |
| **스프린트** | S3 (05.05~05.12) |
| **선행 조건** | Phase 6 Bai-Perron·Chow Test 구조 변화 탐지 완료 |
| **참조 명세** | `doc1_technical_pipeline_vN.md §Phase 7`, `doc2_pattern_definitions_vN.md` |

**구현 범위**

| 패턴 | 내용 | 적용 구간 |
|------|------|-----------|
| 패턴 1 | 방향 역전 및 전달 시차 이탈 탐지 | A·B·C·D·D′ |
| 패턴 2 | 전이율 크기 이탈 (롤링 Z-score + IQR 동시 초과) | A·B·C·D·D′ |
| 패턴 2 비대칭 | 로켓-깃털 효과 (TECM/비대칭 VAR 상승·하락 속도 차) | **A·B만** (구간 C·D 제외) |
| 패턴 3 | 국제가 안정기 중 하류 스프레드 누적 확대 | B |

**DB 적재 대상**: `anomaly_results` 테이블 (신규 Alembic migration 수동 작성)

**팀 검토 항목**
- 임계값 3종 (Z-score 2.0/2.5, IQR 1.5, 안정기 ±3%) 합의
- 패턴별 탐지 결과 샘플 품목(밀·바나나) 교차 검토
- `pipeline_output_spec_vN.md §Phase 7` 출력 형식 준수 확인

**완료 기준**
- 전 10품목 × 전 구간 패턴 1~3 탐지 완료
- 임계값 팀 전원 합의 기록 (`docs/results/phase7-threshold.md`)
- `anomaly_results` 테이블 적재 및 필드 형식 확인
- `pipeline_output_spec_vN §Phase 7` 출력 불일치 0건

**절대 금지**
- Phase 8 신뢰도 최종 판정을 이 Phase에서 선행 수행
- 임계값 단독 결정 (반드시 팀 합의 후 settings.py 반영)

---

### feat/phase7-ml — ML 보조 이상 탐지

| 항목 | 내용 |
|------|------|
| **리드** | 예병성 초안 → 팀 4인 검토 후 확정 |
| **브랜치** | `feat/phase7-ml` |
| **스프린트** | S4 (05.12~05.19) |
| **선행 조건** | `feat/phase7-stat` 완료 (통계 탐지 결과 확정) |
| **참조 명세** | `doc1_technical_pipeline_vN.md §Phase 7-ML`, `doc3_research_proposal_vN.md §8` |

**구현 범위**

| 항목 | 내용 |
|------|------|
| 모델 3종 | Isolation Forest, LOF(Local Outlier Factor), One-Class SVM |
| 입력 피처 | 6종 고정 (Phase 0~4 산출 원시 지표만. 통계 판정값 입력 금지) |
| 학습 단위 | 품목별·구간별 독립 학습 (교차 품목 혼합 금지) |
| 신뢰도 등급화 | 고신뢰(통계+ML 동시), 중신뢰(통계 확인+ML 미탐지), 참고(ML 확인+통계 미탐지) |
| DB 적재 | `ml_scores`, `ml_projections` 테이블 (신규 Alembic migration 수동 작성) |

**팀 검토 항목**
- 6종 피처 구성 최종 확인 (순환 논리 없음 검증)
- 모델별 이상 점수 분포 샘플 품목(밀·바나나) 교차 검토
- 신뢰도 등급화 결과 전 품목 전원 확인

**완료 기준**
- 3모델 전 10품목 × 전 구간 학습·예측 완료
- 신뢰도 등급 전 품목 배정 완료
- `ml_scores`, `ml_projections` 테이블 적재 확인
- CONTAMINATION, RANDOM_STATE settings.py 참조 확인 (하드코딩 금지)

**절대 금지**
- Phase 7 통계 판정값(`confidence_grade`, `stat_flag`)을 입력 피처로 사용 (순환 논리)
- 딥러닝 모델 도입 (LSTM, Transformer, Autoencoder) — 구간 분절로 관측치 부족
- `CONTAMINATION=0.10`, `RANDOM_STATE=42` 코드 하드코딩

---

## 백엔드 (샤킬라 리드)

### feat/be-api-reference — 참조 엔드포인트 5개

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-api-reference` |
| **스프린트** | S2 (04.28~05.05) |
| **선행 조건** | `frame/backend` dev 머지 완료 |
| **참조 명세** | `api_spec_vN.md §참조 엔드포인트` |

**구현 엔드포인트 5개**

| 엔드포인트 | 설명 | 우선순위 |
|------------|------|----------|
| `GET /commodities` | 품목 목록 + 이달 이상 배지 | P0 |
| `GET /commodities/{commodity_id}` | 단일 품목 상세 + segment_meta | P0 |
| `GET /segments` | 분석 구간 정의 목록 (정적) | P1 |
| `GET /events` | 외부 충격 이벤트 목록 (정적) | P1 |
| `GET /freshness` | 데이터 기준 시점 + 다음 갱신 예정일 | P1 |

**세부 구현 요건**
- `/commodities` — `has_anomaly_this_month`, `latest_anomaly_grade` 필드 포함 (DB Phase 7 완료 전: 더미 null)
- `/commodities/{id}` — `segment_meta` 전체 구간(A/B/C/D/D′) 포함, 기준선은 전체 기간(`baselines.subperiod_id IS NULL`)만 반환 (D-15)
- `/commodities/{id}` — `warmup_end` 필드: `baselines.warmup_end` 직접 반환 (별도 집계 없음, D-06)
- `/segments`, `/events` — `ETag` + `Cache-Control: max-age=86400` 헤더 포함
- `/freshness` — `pipeline_runs` 테이블 최신 row 기반 `last_updated` + 수동 입력 `next_update` 반환

**완료 기준**
- 5개 엔드포인트 200 OK 확인 (더미 DB 기반)
- `api_spec_vN.md` 응답 필드명·타입 일치 (불일치 0건)
- snake_case 필드명 유지 (alias 변환 없음)

---

### feat/be-api-anomaly — 이상 탐지 요약 엔드포인트

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-api-anomaly` |
| **스프린트** | S2 후반~S3 (Phase 7-stat 완료 시점에 맞춰 실제 데이터 연동) |
| **선행 조건** | `frame/backend` dev 머지 완료 (더미), `feat/phase7-stat` 완료 (실제 연동) |
| **참조 명세** | `api_spec_vN.md §요약 엔드포인트` |

**구현 엔드포인트 1개**

| 엔드포인트 | 설명 |
|------------|------|
| `GET /anomalies/summary` | 이달의 이상 요약 배너 데이터 |

**세부 구현 요건**
- 이번 달 이상 품목 목록 + 신뢰도 배지 + 지난달 대비 증감 수치
- 이상 없는 달: `anomalies: []` 반환 (null 아님)
- `anomaly_results` 테이블 기반 집계 쿼리

**완료 기준**
- 더미 데이터 기반 200 OK 확인
- Phase 7-stat 완료 후 실제 DB 데이터 연동 확인

---

### feat/be-api-timeseries — 시계열 시각화 엔드포인트

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-api-timeseries` |
| **스프린트** | S3 (05.05~05.12) |
| **선행 조건** | `feat/phase7-stat` 완료 (이상 노드 데이터 필요) |
| **참조 명세** | `api_spec_vN.md §시각화 엔드포인트` |

**구현 엔드포인트 5개**

| 엔드포인트 | 설명 |
|------------|------|
| `GET /commodities/{id}/stream` | 스트림 그래프 시계열 + 이상 노드 |
| `GET /commodities/{id}/stream/minimap` | 스트림 전체 기간 압축 (yearly 고정) |
| `GET /commodities/{id}/scatter` | 전달 구조 산점도 (구간별 상류·하류 변화율) |
| `GET /commodities/{id}/raw-prices` | 원시 시계열 (레이아웃 1~6, 2020=100 지수) |
| `GET /commodities/{id}/raw-prices/minimap` | 원시 시계열 미니맵 |

**세부 구현 요건**
- 시계열 공통 쿼리 파라미터: `from`, `to`, `granularity` (monthly/quarterly/yearly)
- 시계열 공통 응답 envelope: `requested_from`, `actual_from`, `granularity`, `total_points` 필수 포함
- `/stream` — 이상 노드에 `has_anomaly: true`, `anomaly_ids[]` 포함. 집계 granularity와 무관하게 이상 노드는 원본 월 단위 반환
- `/scatter` — `until` 파라미터 지원 (`until > to`이면 `UNTIL_EXCEEDS_TO` 400 반환)
- `/raw-prices` — `layout` 파라미터 1~6. 레이아웃 4(도매가 포함)를 3구간 품목에 요청하면 `WHOLESALE_NOT_AVAILABLE` 400. 레이아웃 5는 PPI-CPI 자동 폴백 (에러 아님, D-12)
- Redis TTL 캐싱 대상 (`/stream`, `/raw-prices`): 캐싱 로직은 `feat/be-redis`에서 추가. 이 브랜치에서는 캐싱 없이 DB 직접 조회

**에러 코드 구현 필수**
`INVALID_SEGMENT`, `INVALID_DATE_RANGE`, `INVALID_LAYOUT`, `WHOLESALE_NOT_AVAILABLE`, `INVALID_GRANULARITY`, `UNTIL_EXCEEDS_TO`, `COMMODITY_NOT_FOUND`, `WARMUP_PERIOD_ONLY`, `PIPELINE_DATA_MISSING`

**완료 기준**
- 5개 엔드포인트 실제 DB 데이터 기반 200 OK 확인
- 3구간·4구간 품목 각 1개씩 실제 시계열 반환 확인
- granularity 3종 동작 확인 (monthly/quarterly/yearly)
- 에러 케이스 400/404 응답 형식 확인

---

### feat/be-api-panel — 분석 수치 패널 엔드포인트

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-api-panel` |
| **스프린트** | S4 (05.12~05.19) |
| **선행 조건** | `feat/phase7-ml` 완료 (ML 결과 데이터 필요) |
| **참조 명세** | `api_spec_vN.md §패널 엔드포인트` |

**구현 엔드포인트 5개**

| 엔드포인트 | 설명 |
|------------|------|
| `GET /anomalies/{anomaly_id}/detail` | 패널 전체 통합 (통계 수치·ML 판정·판정 경로) |
| `GET /anomalies/{anomaly_id}/stat-series` | 패널 내 지표별 인라인 시계열 4종 |
| `GET /anomalies/{anomaly_id}/stat-snapshot` | 비시계열 지표 스냅샷 (IQR 박스플롯·비대칭 히스토그램) |
| `GET /anomalies/{anomaly_id}/irf` | IRF 차트 데이터 (전체 기간 + 하위 기간별) |
| `GET /anomalies/{anomaly_id}/ml-map` | ML 결과맵 2D 투영 데이터 (model 파라미터 필수) |

**세부 구현 요건**
- `/detail` — `judgment_path` 필드에 패턴별 판정 템플릿 기반 근거 텍스트 포함 (D-04)
- `/stat-series` — `metric` 파라미터: `transmission_rate`, `zscore`, `ect`, `spread` 4종만 허용. `iqr`·`asymmetry` 요청 시 `SNAPSHOT_METRIC_ON_SERIES` 400 반환
- `/stat-snapshot` — `metric` 파라미터: `iqr`(박스플롯용), `asymmetry`(히스토그램용) 2종
- `/irf` — `include_subperiods` 파라미터(기본 true). 하위 기간별 IRF 곡선 + CI 포함
- `/ml-map` — `model` 파라미터 필수 (`isolation_forest`·`lof`·`ocsvm`). `projection_method` 기본값 `pca`. OI-15 확정 전까지 pca 고정 구현
- `ANOMALY_NOT_FOUND`, `ML_MAP_NOT_READY`, `INVALID_METRIC`, `SNAPSHOT_METRIC_ON_SERIES` 에러 코드 구현

**완료 기준**
- 5개 엔드포인트 실제 DB 데이터 기반 200 OK 확인
- `/ml-map` 3모델 각각 응답 확인
- `/irf` 전체 기간 + 하위 기간 분리 응답 확인
- 에러 케이스 응답 형식 확인

---

### feat/be-api-meta — 방법론 엔드포인트

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-api-meta` *(be-api-reference와 동시 진행 가능)* |
| **스프린트** | S2 |
| **선행 조건** | `frame/backend` dev 머지 완료 |
| **참조 명세** | `api_spec_vN.md §방법론 엔드포인트` |

**구현 엔드포인트 2개**

| 엔드포인트 | 설명 |
|------------|------|
| `GET /meta/pipeline` | 파이프라인 플로우 노드-엣지 (D3.js 소비 형식) |
| `GET /meta/analysis-params` | 파이프라인 파라미터 기준값 + 패턴 정의 |

**세부 구현 요건**
- 두 엔드포인트 모두 DB 조회 없이 코드 내 정적 딕셔너리로 구현
- `ETag` + `Cache-Control: max-age=86400` 헤더 포함
- `/meta/pipeline` — 노드 11개, 엣지 11개 (api_spec_vN §방법론 예시 JSON 그대로)
- `/meta/analysis-params` — `rolling_window`, `zscore_warning/alert`, `iqr_multiplier`, `stability_threshold`, `pattern3_n_values`, `chow_test_points` 포함. 값은 settings.py 참조

**완료 기준**
- 2개 엔드포인트 200 OK 확인
- 응답 JSON 구조가 api_spec_vN 예시와 일치

---

### feat/be-db-pipeline — 파이프라인 결과 DB 적재

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-db-pipeline` |
| **스프린트** | S3 (05.05~05.12) |
| **선행 조건** | `frame/backend` dev 머지 완료, Phase 2~3 출력 CSV 파일 존재 |
| **참조 명세** | `db_schema_vN.md`, `pipeline_output_spec_vN.md` |

**구현 범위**

| 항목 | 내용 |
|------|------|
| Alembic 추가 migration | Phase 2~3 결과 테이블 (`stationarity_results`, `cointegration_results`) 수동 작성 |
| Phase 4~5 테이블 | `model_params`, `irf_data`, `baselines`, `granger_results` migration 작성 |
| 적재 스크립트 | 파이프라인 CSV 출력 → PostgreSQL INSERT (단일 트랜잭션 묶음) |
| 롤백 처리 | Phase 적재 단위 실패 시 해당 Phase 전체 롤백 |
| `pipeline_runs` 기록 | 적재 시작·완료·실패 상태 기록 |

**완료 기준**
- Phase 2~3 결과 실제 DB 적재 확인 (샘플 품목 밀·바나나 기준)
- 트랜잭션 롤백 동작 확인 (의도적 실패 테스트)
- `pipeline_runs` 실행 이력 1건 이상 정상 기록
- 월초(YYYY-MM-01) 이외 날짜 INSERT 시 `DB-TYPE-001` 예외 발생 확인

---

### feat/be-batch — APScheduler 월별 자동 배치

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-batch` |
| **스프린트** | S4 (05.12~05.19) |
| **선행 조건** | `feat/be-api-reference` 완료 |
| **참조 명세** | `web_plan_vN.md §11.2`, `frame_spec_backend_vN.md §8.7` |

**구현 범위**
- APScheduler v3.10.4 기반 월별 파이프라인 실행 스케줄 등록
- 매월 15일 자동 실행 (수동 트리거 엔드포인트도 개발용으로 추가)
- 배치 실행 결과 `pipeline_runs` 테이블 기록
- 배치 실패 시 ERROR 레벨 구조화 로그 출력

**완료 기준**
- 로컬에서 수동 트리거로 배치 실행 → `pipeline_runs` 기록 확인
- 실패 시나리오 로그 출력 확인

---

### feat/be-redis — Redis 캐싱 적용

| 항목 | 내용 |
|------|------|
| **리드** | 샤킬라 |
| **브랜치** | `feat/be-redis` |
| **스프린트** | S5 (05.19~06.02) |
| **선행 조건** | `feat/be-db-pipeline` 완료 |
| **참조 명세** | `api_spec_vN.md §설계 원칙 6, §미결 사항 캐시 키 규칙` |

**구현 범위**

| 대상 | 캐싱 방식 |
|------|-----------|
| `/stream`, `/raw-prices`, `/stat-series` | Redis TTL 캐싱 |
| `/meta/pipeline`, `/meta/analysis-params`, `/segments`, `/events` | ETag 기반 조건부 캐싱 (이미 be-api에서 헤더 설정 완료) |
| 배치 갱신 후 | `pipeline_runs.id` 기반 캐시 무효화 트리거 |

> **미결**: Redis TTL 값 및 캐시 무효화 전략 상세는 S6 착수 시 `api_spec_vN.md §미결 사항` 기준으로 확정.

**완료 기준**
- `/stream` 첫 요청 DB 조회, 두 번째 요청 Redis 캐시 반환 확인
- 배치 갱신 후 캐시 무효화 → 세 번째 요청 DB 재조회 확인

---

## 프론트엔드 (하대수 리드)

### feat/fe-layout-filter — 레이아웃 + 필터 바

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-layout-filter` |
| **스프린트** | S3 (05.05~05.12) |
| **선행 조건** | `frame/frontend` dev 머지 완료 |
| **참조 명세** | `web_plan_vN.md §3, §4` |

**구현 범위**

| 컴포넌트 | 세부 내용 |
|----------|-----------|
| `AppShell` | Header + FilterBar + MainArea + Panel 3분할 실제 레이아웃 구성 |
| `Header` | 서비스명, 품목 선택 드롭다운(주 품목 + 보조 품목), 뷰 탭(흐름/전달구조/원시시계열), 방법론 탭, 데이터 기준 시점 표시 |
| `Banner` | 상단 이달의 이상 요약 배너 (품목 배지, 지난달 대비 증감, 배지 클릭 시 해당 품목 이동) |
| `FilterBar` | 기간 프리셋 6종(3개월·6개월·1년·3년·5년·전체), 사건 필터 토글 드롭다운, 신뢰도 필터(고신뢰·중신뢰·참고), 패턴 필터(패턴1·2·3), 구간 on/off 토글 |
| `useAppStore` | 선택 품목, 보조 품목, 기간 범위, 필터 상태, 현재 뷰 탭 Zustand 상태 실제 구현 |

**완료 기준**
- 품목 드롭다운 선택 → Header 품목명 변경 확인
- 기간 프리셋 클릭 → from/to 상태 변경 확인
- 필터 선택 상태 Zustand store에 반영 확인
- 더미 데이터 기반 배너 렌더링 확인

---

### feat/fe-stream-chart — 스트림 그래프

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-stream-chart` |
| **스프린트** | S3 (05.05~05.12) |
| **선행 조건** | `frame/frontend` dev 머지 완료 |
| **참조 명세** | `web_plan_vN.md §4~§5`, `api_spec_vN.md §/stream` |

**구현 범위**

| 항목 | 세부 내용 |
|------|-----------|
| D3.js 스트림 그래프 | 품목별 구간(A·B·D′ 또는 A·B·C·D) 전이율 연속 곡선 |
| Y축 | 전이율 직접값 (백분율 아님) |
| 이상 노드 | 고신뢰: 빨강 원, 중신뢰: 주황 원, 참고: 회색 원. 노드 크기는 일정 |
| 노드 클릭 | `useAppStore`에 `selectedAnomalyId` 저장 → 패널 슬라이드인 트리거 |
| 호버 툴팁 | 시점·전이율·이상 신뢰도 등급 표시 |
| 구간 on/off | FilterBar 구간 토글 상태 반영하여 구간 곡선 표시/숨김 |
| 사건 오버레이 | `/events` 데이터 기반 배경 음영 오버레이 (프론트 클라이언트 처리, D-09) |
| 마우스 휠 줌 | X축 기간 확대/축소 지원 |
| 더미 데이터 | `VITE_USE_MOCK=true` 시 fixtures 기반 렌더링 |

**완료 기준**
- 더미 데이터 기반 D3 스트림 그래프 3개 구간 곡선 렌더링 확인
- 이상 노드 3색 표시 확인
- 노드 클릭 시 `selectedAnomalyId` 스토어 반영 확인
- 구간 토글 동작 확인

---

### feat/fe-minimap — 미니맵

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-minimap` |
| **스프린트** | S3 후반 |
| **선행 조건** | `feat/fe-stream-chart` 완료 |
| **참조 명세** | `web_plan_vN.md §5.1`, `api_spec_vN.md §/stream/minimap` |

**구현 범위**
- 스트림 그래프 하단 고정 미니맵 (전체 기간 yearly 압축 뷰)
- 뷰포트 범위 표시 핸들 (드래그로 메인 그래프 기간 이동)
- 원시 시계열 뷰 전용 미니맵도 동일 컴포넌트 재사용

**완료 기준**
- 미니맵 전체 기간 렌더링 확인
- 핸들 드래그 → 메인 그래프 기간 이동 확인

---

### feat/fe-panel — 분석 수치 패널

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-panel` |
| **스프린트** | S4 (05.12~05.19) |
| **선행 조건** | `feat/fe-stream-chart` 완료 (노드 클릭 트리거 필요) |
| **참조 명세** | `web_plan_vN.md §6`, `api_spec_vN.md §패널 엔드포인트` |

**구현 범위**

| 섹션 | 세부 내용 |
|------|-----------|
| 패널 슬라이드인 | 이상 노드 클릭 시 우측 패널 슬라이드인 애니메이션 |
| 헤더 | 품목명·구간·시점·신뢰도 배지·패턴명 표시 |
| 통계 수치 섹션 | 전이율·Z-score·IQR 판정·ECT·IRF 피크 시차·TECM α⁺/α⁻ 수치 표시 |
| 지표 인라인 시계열 | 지표 클릭 시 해당 지표 인라인 시계열 차트 펼침 (transmission_rate·zscore·ect·spread) |
| IQR 박스플롯 | 롤링 48개월 IQR 분포 + 현재값 마커 |
| 비대칭 히스토그램 | 상승·하락 국면 전이율 분포 히스토그램 (패턴 2 구간 A·B에서만 표시) |
| IRF 차트 | 전체 기간 + 하위 기간별 IRF 곡선 (D3.js, CI 밴드 포함) |
| ML 판정 섹션 | Isolation Forest·LOF·One-Class SVM 이상 점수 바 차트 + ml_vote |
| ML 결과맵 | 모델 탭 선택 → 2D 투영 산점도 (현재 이상 노드 하이라이트) |
| 판정 경로 뷰 | 패턴별 판정 흐름 텍스트 표시 (`judgment_path`) |
| 더미 데이터 | `VITE_USE_MOCK=true` 시 fixtures 기반 패널 렌더링 |

**완료 기준**
- 더미 데이터 기반 패널 전 섹션 렌더링 확인
- 슬라이드인 애니메이션 동작 확인
- 지표 클릭 → 인라인 시계열 펼침 동작 확인
- ML 모델 탭 전환 → 결과맵 교체 확인

---

### feat/fe-scatter-chart — 전달 구조 산점도

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-scatter-chart` |
| **스프린트** | S4 후반 |
| **선행 조건** | `feat/fe-panel` 완료 |
| **참조 명세** | `web_plan_vN.md §5.2`, `api_spec_vN.md §/scatter` |

**구현 범위**
- D3.js 기반 상류·하류 가격 변화율 산점도
- 과대 전달 구역(우상단), 과소 전달 구역(우하단), 역전달 구역(좌측) 색상 구분 영역 표시
- 현재 선택 시점 강조 마커
- `until` 슬라이더: 특정 시점까지의 데이터만 표시 (누적 변화 확인용)
- 구간 탭: A·B·C·D 구간별 전환 (web_plan_vN §5.2 하단 구간 탭)
- 더미 데이터 기반 렌더링

**완료 기준**
- 더미 데이터 기반 산점도 렌더링 확인
- 구역 색상 구분 확인
- `until` 슬라이더 동작 확인

---

### feat/fe-raw-timeseries — 원시 시계열 뷰

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-raw-timeseries` |
| **스프린트** | S4 후반 |
| **선행 조건** | `feat/fe-layout-filter` 완료 |
| **참조 명세** | `web_plan_vN.md §5.3`, `api_spec_vN.md §/raw-prices` |

**구현 범위**

| 레이아웃 번호 | 구성 |
|---------------|------|
| 레이아웃 1 | 국제가만 |
| 레이아웃 2 | 국제가 + 수입단가 |
| 레이아웃 3 | 국제가 + PPI |
| 레이아웃 4 | 국제가 + 도매가 (4구간 품목만. 3구간 품목 요청 시 에러 처리) |
| 레이아웃 5 | PPI + CPI (3구간 품목은 자동 폴백. 4구간은 선택 가능) |
| 레이아웃 6 | 전체 구간 (3구간: A·B·D′ / 4구간: A·B·C·D) |

- Y축 2020=100 지수 통일
- 레이아웃 선택 바: FilterBar 하단 레이아웃 선택 영역 연동
- 마우스 휠 줌, 미니맵 재사용
- 더미 데이터 기반 렌더링

**완료 기준**
- 레이아웃 6종 전환 확인
- 3구간 품목에서 레이아웃 4 → 에러 처리 확인
- Y축 2020=100 지수 표시 확인

---

### feat/fe-methodology-tab — 방법론 탭

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-methodology-tab` |
| **스프린트** | S5 (05.19~06.02) |
| **선행 조건** | `feat/be-api-meta` 완료 |
| **참조 명세** | `web_plan_vN.md §8` |

**구현 범위**

| 섹션 | 내용 |
|------|------|
| §1 파이프라인 플로우 | `/meta/pipeline` 노드-엣지 기반 D3.js 다이어그램 (어려울 시 SVG 이미지 대체) |
| §2 분석 파라미터 | `/meta/analysis-params` 기반 파라미터 기준값 표 |
| §3 패턴 정의 | 패턴 1·2·3 설명 카드 |
| §4 신뢰도 등급 | 고신뢰·중신뢰·참고 기준 설명 |
| §5 품목·경로 | 3구간·4구간 분류 및 경로(A→B→D′/A→B→C→D) 설명 |
| §6 한계 및 고지 | 탐지 결과 참고 정보 원칙, 인과관계 미확정 고지 |

**완료 기준**
- 6개 섹션 전체 렌더링 확인
- `/meta/pipeline` API 연동 D3 다이어그램(또는 SVG) 표시 확인

---

### feat/fe-onboarding — 온보딩 가이드

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-onboarding` |
| **스프린트** | S5 (05.19~06.02) |
| **선행 조건** | `feat/fe-panel` 완료 (패널 UI 확정 후 가이드 내용 작성 가능) |
| **참조 명세** | `web_plan_vN.md §9` |

**구현 범위**
- 최초 방문 시 자동 실행 인터랙티브 가이드 (4단계)
- 단계 1: 스트림 그래프 읽는 법 (구간·이상 노드 색상 안내)
- 단계 2: 이상 노드 클릭 → 분석 수치 패널 사용법
- 단계 3: 필터 바 활용 (기간·신뢰도·패턴 필터)
- 단계 4: 방법론 탭 안내
- "다시 보지 않기" 옵션 (Zustand 세션 상태로 관리. localStorage 사용 금지)

**완료 기준**
- 4단계 온보딩 순차 동작 확인
- "다시 보지 않기" 후 재접속 시 온보딩 미표시 확인 (세션 내)

---

### feat/fe-api-connect — 실제 API 연동 전환

| 항목 | 내용 |
|------|------|
| **리드** | 하대수 |
| **브랜치** | `feat/fe-api-connect` |
| **스프린트** | S6 (06.02~06.12) |
| **선행 조건** | 전 백엔드 feat 브랜치 dev 머지 완료, end-to-end 동작 확인 완료 |
| **참조 명세** | `api_spec_vN.md 전체` |

**구현 범위**
- `VITE_USE_MOCK=false` 전환 후 전 컴포넌트 실제 API 연동
- React Query 캐싱 설정 (staleTime, gcTime 품목별 최적화)
- API 오류 상태 처리 (로딩 스피너, 에러 메시지, 재시도 버튼)
- end-to-end 시나리오 테스트: 품목 선택 → 스트림 그래프 렌더링 → 이상 노드 클릭 → 패널 표시

**완료 기준**
- 전 18개 엔드포인트 실제 연동 확인
- 10개 품목 각각 스트림 그래프 렌더링 성공
- 에러 케이스(404, 500) UI 처리 확인

---

## 기능 명세 작성 순서 (PM 일정)

| 우선순위 | 기능 명세 대상 | 작성 시점 |
|----------|----------------|-----------|
| 1순위 | `feat/be-api-reference`, `feat/be-api-meta`, `feat/be-db-pipeline` | S2 시작 전 (04.28) |
| 2순위 | `feat/fe-layout-filter`, `feat/fe-stream-chart`, `feat/phase7-stat` | S3 시작 전 (05.05) |
| 3순위 | `feat/be-api-timeseries`, `feat/be-api-anomaly`, `feat/fe-minimap` | S3 시작 전 (05.05) |
| 4순위 | `feat/be-api-panel`, `feat/fe-panel`, `feat/be-batch`, `feat/phase7-ml` | S4 시작 전 (05.12) |
| 5순위 | `feat/fe-scatter-chart`, `feat/fe-raw-timeseries` | S4 시작 전 (05.12) |
| 6순위 | `feat/be-redis`, `feat/fe-methodology-tab`, `feat/fe-onboarding` | S5 시작 전 (05.19) |
| 7순위 | `feat/fe-api-connect` | S6 시작 전 (06.02) |

---

## 브랜치 생성 금지 조건 체크리스트

feat/* 브랜치 생성 전 반드시 확인:

- [ ] sprint_plan 최신 버전 기준 스프린트 일정 확인 (유동적 변경 주의)
- [ ] `frame/backend` dev 머지 완료 (백엔드 관련 feat)
- [ ] `frame/frontend` dev 머지 완료 (프론트엔드 관련 feat)
- [ ] 선행 feat/* 브랜치 완료 (위 표 "선행 조건" 기준)
- [ ] 기능 명세 PM 승인 완료

---

*이 문서는 sprint_plan_vN.md와 함께 운용한다. 스프린트 일정 변경 시 sprint_plan만 갱신하고, 기능 구현 내용 변경 시 이 문서를 갱신한다.*
