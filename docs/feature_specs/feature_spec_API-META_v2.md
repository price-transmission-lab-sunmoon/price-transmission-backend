# Feature 명세서 — 방법론 엔드포인트

**문서 유형**: Feature 명세서  
**기능 번호**: `API-META`  
**브랜치명**: `feat/be-api-meta`  
**담당자**: 바게스타니 샤킬라 (백엔드 리드)  
**작성일**: 2026-05-07  
**변경 이력**:
- v1 (2026-05-07): 최초 작성
- v2 (2026-05-11): 참조 문서 버전 갱신 및 오류 수정. §0 `exception_spec_vN.md` v5→v6, `frame_spec_backend_vN.md` v3→v4. §3.3 `ZSCORE_THRESHOLD_WARNING`→`ZSCORE_WARNING`, `ZSCORE_THRESHOLD_ALERT`→`ZSCORE_ALERT` (`frame_spec_backend_v4 §4` 기\ub4f1록 \ud0a4). §4.1 `ZSCORE_WARNING`·`ZSCORE_ALERT` 기등록 \ud0a4 \ud589 추\uac00. §4.2 해당 \ud589 제\uac70.  
**스프린트**: S2  
**상태**: 초안 / PM 승인 대기

---

## ⚠️ 구현 시작 전 필수 확인

> AI 및 구현 담당자는 아래 문서가 **모두 첨부 또는 열람 가능한 상태**인지 확인한 후 구현을 시작한다.  
> 하나라도 누락된 경우 구현을 시작하지 않고 PM에게 문서 제공을 요청한다.

| 문서 | 버전 | 참조 목적 | 확인 |
|------|------|-----------|------|
| `api_spec_vN.md §방법론 엔드포인트` | v5 | 엔드포인트·응답 필드명·JSON 예시 1:1 구현 기준 | ☐ |
| `exception_spec_vN.md §API-VAL-001, §API-INT-001, §CFG-CORE-001` | v6 | 이 기능에 해당하는 에러 코드·처리 방침 (참조용) | ☐ |
| `exception_design_vN.md` | v3 | 에러 체이닝 구현 방식 (코드 구현용) | ☐ |
| `frame_spec_backend_vN.md §2 디렉토리 구조, §4 환경 변수` | v4 | 파일 생성 위치·`settings.py` 키 참조 규칙 확인 | ☐ |
| `web_plan_vN.md §8.2` | v6 | 방법론 탭 각 섹션이 어느 엔드포인트 데이터를 소비하는지 확인 | ☐ |

---

## 1. 기능 개요

### 1.1 한 줄 요약

방법론 탭(`web_plan_vN §8.2`) 전용 정적 엔드포인트 2개(`/meta/pipeline`, `/meta/analysis-params`)를 구현한다. 두 엔드포인트 모두 DB 조회 없이 코드 내 정적 딕셔너리로 응답하며 `ETag` 조건부 캐싱 헤더를 포함한다.

### 1.2 데이터 흐름

```
코드 내 정적 딕셔너리 (settings.py 파라미터 참조 포함)
  → Pydantic 직렬화
  → ETag 생성 (응답 본문 해시) + Cache-Control: max-age=86400 헤더 설정
  → GET /api/v1/meta/pipeline         → 노드 11개 + 엣지 12개 JSON 응답
  → GET /api/v1/meta/analysis-params  → 파라미터 기준값 + 패턴 정의 JSON 응답
```

### 1.3 프레임 내 위치

`frame_spec_backend_vN.md §2 디렉토리 구조` 기준.

| 구분 | 경로 | 작업 내용 |
|------|------|-----------|
| 수정 | `app/api/v1/endpoints/meta.py` | `/meta/pipeline`, `/meta/analysis-params` 라우터 함수 추가 (Frame 단계 더미 상태에서 실 로직으로 교체) |
| 수정 | `app/schemas/meta.py` | `/meta/pipeline` (`PipelineFlowResponse`) + `/meta/analysis-params` (`AnalysisParamsResponse`) Pydantic DTO 추가 |
| 신규 | `app/services/meta.py` | 정적 딕셔너리 반환 + ETag 생성 로직. DB 세션 의존성 없음 |

### 1.4 구현 범위 및 비구현 범위

| 구분 | 내용 |
|------|------|
| **구현** | `/meta/pipeline` 정적 노드-엣지 응답 (노드 11개, 엣지 12개) + ETag·Cache-Control 헤더 / `/meta/analysis-params` 정적 파라미터·패턴 정의 응답 + ETag·Cache-Control 헤더 |
| **비구현** | Redis TTL 캐싱 로직 (`feat/be-redis` 브랜치 담당 — ETag 헤더 설정은 이 브랜치에서 완료하고 Redis 레이어는 feat/be-redis에서 추가) / 방법론 탭 프론트엔드 렌더링 (`feat/fe-methodology-tab` 담당) |
| **선행 조건** | `frame/backend` dev 머지 완료 (이미 충족 — Frame 커밋 완료 상태) |
| **후속 조건** | `feat/fe-methodology-tab` 착수 가능 상태 (프론트엔드 방법론 탭 선행 조건) |

---

## 2. 입력 데이터

두 엔드포인트 모두 **DB 조회 없음** — 코드 내 정적 딕셔너리 + `settings.py` 파라미터 참조만 사용한다.

| 출처 | 사용 항목 | 엔드포인트 | 비고 |
|------|-----------|------------|------|
| 코드 내 정적 딕셔너리 | 노드 11개, 엣지 12개 정의 | `/meta/pipeline` | `api_spec_vN §/meta/pipeline` 예시 JSON 그대로 |
| 코드 내 정적 딕셔너리 | 패턴 1·2·3 정의, 분석 범위 메타 | `/meta/analysis-params` | `api_spec_vN §/meta/analysis-params` 예시 JSON 그대로 |
| `settings.py` (기존 등록 키) | `ROLLING_WINDOW` | `/meta/analysis-params` | `frame_spec_backend_vN §4` 등록 키 — 즉시 참조 가능. `CONTAMINATION`·`RANDOM_STATE`는 같은 §4 등록 키이나 API 응답에 미노출 (파이프라인 내부 파라미터) |
| `settings.py` (신규 추가 예정 키, ⚠️ PM 승인 후) | `PIPELINE_VERSION`, `IQR_MULTIPLIER`, `STABILITY_THRESHOLD`, `PATTERN3_N_VALUES`, `MIN_SUBPERIOD_OBS`, `LAG_SEARCH_RANGE`, `CHOW_TEST_POINTS` | `/meta/pipeline`, `/meta/analysis-params` | PM 승인 전까지 `app/services/meta.py` `_DEFAULTS` 딕셔너리로 임시 관리 (§4.2) |

### 2.1 타입 변환 규칙

해당 없음 — 두 엔드포인트 모두 DB 타입 변환 없이 정적 값 직렬화만 수행한다.

---

## 3. 출력 데이터 (API 응답)

### 3.1 구현 엔드포인트 목록

| 엔드포인트 | 설명 | 캐싱 방식 |
|------------|------|-----------|
| `GET /api/v1/meta/pipeline` | 파이프라인 플로우 노드-엣지 (D3.js 소비 형식) | `ETag` + `Cache-Control: max-age=86400` |
| `GET /api/v1/meta/analysis-params` | 파이프라인 파라미터 기준값 + 패턴 정의 | `ETag` + `Cache-Control: max-age=86400` |

### 3.2 `/meta/pipeline` 응답 구조

노드 11개, 엣지 12개. `api_spec_vN §/meta/pipeline` 예시 JSON을 1:1로 구현한다.

**노드 목록** (`phase_number` 기준):

| `id` | `label` | `description` | `phase_number` |
|------|---------|---------------|----------------|
| `phase0` | Phase 0 | 데이터 수집·전처리 | 0 |
| `phase1` | Phase 1 | 계절 조정 (STL) | 1 |
| `phase2` | Phase 2 | 정상성 검정 | 2 |
| `phase3` | Phase 3 | 공적분 검정 | 3 |
| `phase4_vecm` | VECM 추정 | 장기 균형 포함 모형 | 4 |
| `phase4_var` | VAR 추정 | 단기 동적 모형 | 4 |
| `phase5` | Phase 5 | Granger 인과 검정 | 5 |
| `phase6` | Phase 6 | 구조 변화 탐지 | 6 |
| `phase7` | Phase 7 | 통계 기반 이상 탐지 | 7 |
| `phase7_ml` | Phase 7-ML | ML 보조 교차검증 | 7.5 |
| `phase8` | Phase 8 | 결과 종합·등급화 | 8 |

**엣지 목록** (12개):

| `source` | `target` | `label` (선택) |
|----------|----------|----------------|
| `phase0` | `phase1` | — |
| `phase1` | `phase2` | — |
| `phase2` | `phase3` | — |
| `phase3` | `phase4_vecm` | 공적분 있음 |
| `phase3` | `phase4_var` | 공적분 없음 |
| `phase4_vecm` | `phase5` | — |
| `phase4_var` | `phase5` | — |
| `phase5` | `phase6` | — |
| `phase6` | `phase7` | — |
| `phase6` | `phase7_ml` | — |
| `phase7` | `phase8` | — |
| `phase7_ml` | `phase8` | — |

> **주의**: `api_spec_v5` 예시 JSON에는 엣지가 11개로 기재됐으나 `phase7_ml → phase8` 엣지가 목록에 포함될 경우 실제 12개임. 구현 시 `api_spec_vN §/meta/pipeline` 예시 JSON 원본을 최종 기준으로 삼는다.

**최상위 응답 필드**:

| 필드 | 타입 | 값 |
|------|------|----|
| `version` | string | `"v8"` — `settings.py` `PIPELINE_VERSION` 키 참조 (하드코딩 금지) |
| `nodes` | array | 위 노드 11개 |
| `edges` | array | 위 엣지 12개 |

### 3.3 `/meta/analysis-params` 응답 구조

`api_spec_vN §/meta/analysis-params` 예시 JSON을 1:1로 구현한다.

**최상위 필드**:

| 필드 | 타입 | 출처 |
|------|------|------|
| `version` | string | `settings.py PIPELINE_VERSION` |
| `params` | object | `settings.py` 파라미터 참조 (§4 참조) |
| `patterns` | array | 코드 내 정적 딕셔너리 (패턴 1·2·3) |

**`params` 객체 필드**:

| 필드 | `settings.py` 키 | 타입 |
|------|-----------------|------|
| `rolling_window` | `ROLLING_WINDOW` | integer |
| `zscore_warning` | `ZSCORE_WARNING` | float |
| `zscore_alert` | `ZSCORE_ALERT` | float |
| `iqr_multiplier` | `IQR_MULTIPLIER` | float |
| `stability_threshold` | `STABILITY_THRESHOLD` | float |
| `pattern3_n_values` | `PATTERN3_N_VALUES` | integer[] |
| `min_subperiod_obs` | `MIN_SUBPERIOD_OBS` | integer |
| `lag_search_range` | `LAG_SEARCH_RANGE` | integer[] |
| `chow_test_points` | `CHOW_TEST_POINTS` | string[] (`YYYY-MM`) |

**`patterns` 배열** (정적 딕셔너리, 3개):

| `pattern_id` | `label_kr` | `description` | `applicable_segments` |
|---|---|---|---|
| `pattern1` | 패턴 1: 방향 역전 및 시차 이탈 | 국제 원자재 가격이 변동할 때 다음 단계 가격이 반대 방향으로 움직이거나, 정상 전달 시차(IRF 피크 시점 + 버퍼 1개월)를 초과해도 하류가 무반응인 경우 | `["A", "B", "C", "D", "D_prime"]` |
| `pattern2` | 패턴 2: 전이율 크기 이탈 및 비대칭 전달(로켓-깃털 효과) | 전이율이 롤링 Z-score와 IQR 기준을 동시 초과하거나, TECM/비대칭 VAR에서 상승·하락 조정 속도가 유의미하게 다른 경우 | `["A", "B"]` |
| `pattern3` | 패턴 3: 국제가격 안정기 중 하류 물가 스프레드 누적 확대 | 국제가 안정기(원화 환산 월 변동 ±3% 이내)에 수입단가-PPI 간 수준 괴리가 N개월 연속 같은 방향으로 확대되는 경우 | `["B"]` |

> **주의**: `description` 필드 문구는 `api_spec_vN §/meta/analysis-params` 예시 JSON 원본 기준으로 확정한다. 임의 수정 시 PM 승인 필요 (§8 금지 사항 참조).

### 3.4 공통 응답 헤더

두 엔드포인트 모두 아래 헤더를 응답에 포함한다.

| 헤더 | 값 | 생성 방식 |
|------|----|-----------|
| `ETag` | `"<응답 본문 SHA-256 해시 앞 16자>"` | `app/services/meta.py`에서 JSON 직렬화 후 해시 생성 |
| `Cache-Control` | `max-age=86400` | 정적 설정 |

`If-None-Match` 요청 헤더가 현재 `ETag`와 일치하는 경우 `304 Not Modified`를 반환한다.

---

## 4. 파라미터 제약 조건

> 이 섹션의 파라미터 값은 코드에 **하드코딩하지 않는다**.  
> `frame_spec_backend_vN §4`에 이미 등록된 키는 `settings.py`에서 참조한다.  
> **미등록 키**(`PIPELINE_VERSION` 등 아래 표의 ⚠️ 항목)는 이 브랜치에서 `settings.py`에 신규 추가 예정이며, **PM 승인 후 추가**한다 (§9 승인 항목 참조).

### 4.1 frame_spec_backend_vN §4에 이미 등록된 키 (즉시 참조 가능)

| 파라미터명 | `settings.py` 키 | 기본값 | 사용 엔드포인트 | 비고 |
|------------|------------------|--------|----------------|------|
| 롤링 윈도우 | `ROLLING_WINDOW` | `48` | `/meta/analysis-params` `params.rolling_window` | API 응답에 노출 |
| Z-score 주의 임계값 | `ZSCORE_WARNING` | `2.0` | `/meta/analysis-params` `params.zscore_warning` | API 응답에 노출 |
| Z-score 경보 임계값 | `ZSCORE_ALERT` | `2.5` | `/meta/analysis-params` `params.zscore_alert` | API 응답에 노출 |
| ML 이상 비율 | `CONTAMINATION` | `0.10` | — | **API 응답 미노출** — 파이프라인·ML 내부 파라미터. `api_spec_vN §/meta/analysis-params` 예시 JSON의 `params` 객체에 없음 |
| ML 난수 시드 | `RANDOM_STATE` | `42` | — | **API 응답 미노출** — 파이프라인·ML 내부 파라미터. `api_spec_vN §/meta/analysis-params` 예시 JSON의 `params` 객체에 없음 |

### 4.2 이 브랜치에서 settings.py에 신규 추가 예정인 키 (⚠️ PM 승인 필요)

| 파라미터명 | `settings.py` 키 (신규) | 기본값 | 하드코딩 금지 이유 |
|------------|------------------------|--------|-------------------|
| 파이프라인 버전 | `PIPELINE_VERSION` | `"v8"` | 파이프라인 갱신 시 단일 지점 변경 |
| IQR 배수 | `IQR_MULTIPLIER` | `1.5` | 로버스트니스 분석 대상 |
| 안정 구간 임계값 | `STABILITY_THRESHOLD` | `0.03` | 패턴 3 탐지 민감도 조절 대상 |
| 패턴 3 N값 목록 | `PATTERN3_N_VALUES` | `[2, 3, 6]` | 패턴 3 기준 N 변경 가능 |
| 최소 하위 기간 관측치 | `MIN_SUBPERIOD_OBS` | `60` | 구조 변화 탐지 파라미터 |
| 시차 탐색 범위 | `LAG_SEARCH_RANGE` | `[1, 4]` | Phase 3 AIC 탐색 범위 |
| 구조 변화 검정 시점 | `CHOW_TEST_POINTS` | `["2008-01", "2020-01", "2022-01"]` | 외부 충격 이벤트 기반, 변경 가능 |

> **PM 승인 전 임시 처리**: 신규 키 PM 승인 전까지는 `api_spec_vN §방법론 엔드포인트` 예시 JSON 값을 코드 내 모듈 상수(`app/services/meta.py` 상단 `_DEFAULTS` 딕셔너리)로 분리하여 정의한다. 하드코딩 금지 원칙 준수를 위해 응답 생성 코드가 `_DEFAULTS`를 참조하도록 작성하고, PM 승인 후 `settings.py` 키 참조로 교체한다.

---

## 5. 예외처리

> - **`exception_spec_vN.md`**: 에러 코드 인덱스. 이 기능에 해당하는 코드의 발생 조건·처리 방침 확인 시 참조한다. (반복 조회용)
> - **`exception_design_vN.md`**: 에러 체이닝 구현 설계. 실제 코드 작성 시 이 문서의 구현 패턴을 따른다. (코드 구현용)

### 5.1 적용 예외 코드

| 예외 코드 | 발생 조건 | 처리 방침 |
|-----------|-----------|-----------|
| `API-VAL-001` | Pydantic 직렬화 실패 (정적 딕셔너리 구조 오류, 타입 불일치 등 — 정상 운영 중 발생 불가, 배포 전 테스트에서 잡아야 함) | **400** CLIENT_400 (`context`에 `loc`, `input` 보존) |
| `API-INT-001` | 전역 예외 핸들러에 매핑되지 않은 내부 예외 발생 (예상치 못한 Python 예외) | **500** `INTERNAL_ERROR` — 사용자에게 내부 코드 노출 금지, 내부 로그에만 상세 기록 (`exception_spec_vN §부록 A` 핸들러 매핑 기준) |

> **비고**: 두 엔드포인트는 DB 조회·파라미터 수신이 없으므로 적용되는 예외 코드가 최소화된다. `settings.py` 로딩 실패는 `CFG-CORE-001` (FATAL, 서버 기동 중단)로 처리되며 본 기능 범위 외다.

---

## 6. 목업 및 실제 데이터 전환 조건

| 항목 | 내용 |
|------|------|
| 더미 → 실제 전환 | 해당 없음 — 두 엔드포인트 모두 정적 응답이므로 DB 연동 전환 단계 없음 |
| 프론트엔드 연동 전환 트리거 | `VITE_USE_MOCK=false` 전환 후 프론트엔드가 실제 `/meta/pipeline`, `/meta/analysis-params` API를 호출하도록 전환 (`feat/fe-methodology-tab` 착수 전 확인) |
| 목업 파일 위치 | `tests/fixtures/meta_pipeline.json`, `tests/fixtures/meta_analysis_params.json` |
| 테스트 방식 | `api_spec_vN §/meta/pipeline`, `§/meta/analysis-params` 예시 JSON과 응답 1:1 비교 |
| ETag 검증 | 동일 요청 2회 시 첫 응답 `ETag` 값과 두 번째 `If-None-Match` 헤더 일치 → `304 Not Modified` 반환 확인 |

---

## 7. 완료 기준

> 주관적 판단이 개입되지 않도록 수치·상태로 기술한다.

| 항목 | 기준 |
|------|------|
| 기능 완성 | 2개 엔드포인트 200 OK 확인 |
| 출력 형식 | `api_spec_vN §방법론 엔드포인트` 예시 JSON과 응답 필드명·타입·값 일치, 누락 0개 |
| 노드·엣지 수 | `/meta/pipeline` 응답 노드 11개, 엣지 12개 (api_spec_vN 원본 기준) 확인 |
| 파라미터 | `settings.py` 등록 키 중 API 응답 노출 키(`ROLLING_WINDOW`, `ZSCORE_WARNING`, `ZSCORE_ALERT`) 참조 확인 / 신규 키는 `_DEFAULTS` 딕셔너리 분리 확인 — 하드코딩 0건. `CONTAMINATION`·`RANDOM_STATE`는 API 응답 미노출 확인 |
| ETag 동작 | 동일 요청 2회 — 첫 응답 ETag 수신 → `If-None-Match` 재요청 시 `304 Not Modified` 반환 확인 |
| Cache-Control | 응답 헤더에 `Cache-Control: max-age=86400` 포함 확인 |
| 예외처리 | `API-VAL-001` — 정적 딕셔너리 타입 오류 시 **400** 응답 구조 확인 (`context.loc`, `context.input` 포함) / `API-INT-001` — 미매핑 예외 발생 시 **500** `INTERNAL_ERROR` 응답, 내부 코드 미노출 확인 |
| 스키마 일치 | `api_spec_vN` ↔ `app/schemas/meta.py` Pydantic DTO 필드명 불일치 0건 |
| 후속 선행 조건 | `feat/fe-methodology-tab` 착수 가능 상태 |

---

## 8. 금지 사항

| 금지 사항 | 이유 |
|-----------|------|
| §4 파라미터 값 코드 하드코딩 (`ROLLING_WINDOW=48`, `"version": "v8"` 등) | `settings.py` 단일 관리 원칙 위반 |
| DB 세션 의존성 주입 (`get_db` 등) | 두 엔드포인트는 정적 응답 — DB 연결 불필요, 불필요한 커넥션 낭비 |
| `exception_spec_vN` 미등록 예외 코드 임의 생성 | `exception_spec §사용 규칙` 위반. 신규 상황은 `(proposed)` 표식 후 PM 리뷰 필수 |
| API 응답 필드명 camelCase 변환 (`alias_generator`) | `frame_spec_backend_vN §6.1` 정책 위반 (snake_case 통일) |
| Redis 캐싱 로직 이 브랜치에서 추가 | `feat/be-redis` 브랜치 담당 범위. 이 브랜치는 ETag 헤더 설정까지만 구현 |
| 패턴 정의 텍스트(`description`, `label_kr`) 임의 수정 | `api_spec_vN §방법론 엔드포인트` 예시 JSON 원본 기준 — 변경 시 PM 승인 필요 |
| `frame_spec_backend_vN §4` 미등록 신규 `settings.py` 키를 PM 승인 없이 추가 | `frame_spec §4` 환경 변수 목록 단일 관리 원칙 위반 (§4.2 참조) |

---

## 9. PM 승인

| 항목 | 확인 |
|------|------|
| 2개 엔드포인트가 `api_spec_vN §방법론 엔드포인트`와 정합한가 | ☐ |
| 노드 11개·엣지 수가 `api_spec_vN` 원본과 일치하는가 (엣지 11개 vs 12개 최종 확인) | ☐ |
| §4.1 기존 `settings.py` 키 중 API 응답 노출 키(`ROLLING_WINDOW`·`ZSCORE_WARNING`·`ZSCORE_ALERT` 3종)가 참조 원칙을 따르는가 (`CONTAMINATION`·`RANDOM_STATE`는 응답 미노출 확인) | ☐ |
| §4.2 신규 `settings.py` 키 7종 추가를 승인하는가 (`PIPELINE_VERSION` 등 — `frame_spec_backend_vN §4` 갱신 연동 필요) | ☐ |
| PM 승인 전 임시 `_DEFAULTS` 딕셔너리 방식을 허용하는가 | ☐ |
| ETag + Cache-Control 헤더 정책이 `feat/be-redis` 범위와 충돌 없는가 | ☐ |
| `feat/fe-methodology-tab` 선행 조건으로 이 브랜치가 맞는가 | ☐ |

**승인일**: ____________________  
**승인자**: PM 최수안

---

## 10. Pull Request 템플릿

> `feat/be-api-meta` → `dev` PR 작성 시 아래 본문을 복사하여 채운다.

```markdown
## 개요
- **브랜치**: feat/be-api-meta
- **기능 번호**: API-META
- **Feature 명세**: docs/feature_spec_API-META_v2.md
- **담당자**: 바게스타니 샤킬라

## 구현 완료 항목
Feature 명세 §7 완료 기준 기준으로 체크한다.
- [ ] 기능 완성: 2개 엔드포인트 200 OK 확인
- [ ] 출력 형식 준수 (api_spec_vN 예시 JSON과 필드명·타입·값 일치, 누락 0개)
- [ ] 노드 11개, 엣지 수 확인 (api_spec_vN 원본 기준)
- [ ] 파라미터 settings.py 기존 키 참조 확인 / 신규 키는 _DEFAULTS 분리 확인 (하드코딩 0건)
- [ ] ETag 동작 확인 (If-None-Match → 304 Not Modified)
- [ ] Cache-Control: max-age=86400 헤더 포함 확인

## 스키마 일치 확인
- [ ] api_spec_vN ↔ app/schemas/meta.py Pydantic DTO 필드명 일치
- 불일치 항목: {없음 / 목록}

## 예외처리 범위
- 적용 예외 코드: API-VAL-001, API-INT-001
- 신규 제안 코드: {없음 / (proposed) 표식 포함 목록}

## 로컬 실행 증빙
{로그·스크린샷·테스트 출력 붙여넣기}

## 리뷰어 확인 요청 사항
- api_spec_vN 원본 기준 엣지 수 (11개 vs 12개) 최종 확인 요청

## 기타
- Redis 캐싱은 feat/be-redis에서 추가 예정
- DB 세션 의존성 없음 확인 (정적 응답 전용)
```
