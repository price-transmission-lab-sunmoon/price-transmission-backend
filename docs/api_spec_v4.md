# API 명세서

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: FastAPI 백엔드 API 명세서 (v3)
**작성일**: 2026-04-20
**작성 기준**: db_schema_v2 / web_plan_v6 / pipeline_output_spec_v5
**변경 이력**:
- v1 → v2: 시계열 청크·해상도 구조 전면 보완. `granularity` 파라미터 신설. 미니맵 전용 엔드포인트 분리. 응답 envelope에 범위 echo-back·total_points 추가. `stat-series` 비시계열 metric 분리. breakpoints 중복 제거. scatter 슬라이더 파라미터 추가. 정적 엔드포인트 버전 필드 추가. 에러코드 보완.
- v2 → v3: design_review_v1 검토 반영. 주요 변경: D-04(judgment_path 생성 주체·패턴별 템플릿 명시), D-06(warmup_end 출처 명시), D-09(이벤트 오버레이 정책 명시), D-11(날짜 직렬화 방침 명시), D-12(raw-prices 레이아웃 5 폴백 정책 확정), D-15(segment_meta 기준선 선택 규칙 명시), D-16(stat-series breakpoints 출처 오기 수정), D-20(에러 envelope context 필드 추가).
- v3 → v4: pipeline_output_spec v5 반영. 작성 기준 버전 갱신. lag_search_range가 Phase 3 소관임을 주석으로 명시.

---

## 개요

### 설계 원칙

1. **재사용성 우선** — 출력 구조가 유사한 요청은 쿼리 파라미터로 분기하여 엔드포인트를 통합한다.
2. **읽기 전용** — 전 엔드포인트 GET 방식. 쓰기는 배치 파이프라인이 직접 DB에 적재하며 API를 통하지 않는다.
3. **과적재 원칙** — 파이프라인 출력 미확정 구간(Phase 3~7)의 응답 필드는 넉넉하게 정의한다. 검수 후 불필요한 필드는 제거한다.
4. **청크 단위 시계열** — 시계열 엔드포인트는 `from`/`to`로 범위를 한정하고 `granularity`로 집계 단위를 조절한다. 전체 기간 압축 표현(미니맵)은 별도 엔드포인트로 분리한다.
5. **응답 envelope** — 시계열 응답은 항상 서버가 실제로 잘라준 범위(`actual_from`/`actual_to`)와 총 포인트 수(`total_points`)를 포함하여 프론트엔드가 범위를 검증할 수 있도록 한다.
6. **Redis 캐싱** — 시계열 조회(`/stream`, `/raw-prices`, `/stat-series`)는 Redis TTL 캐싱 대상. 정적 데이터(`/meta/*`, `/segments`, `/events`)는 `ETag` 기반 조건부 캐싱.
7. **이벤트 오버레이 정책 (D-09)** — 이벤트 배경 음영은 `/events` 엔드포인트를 별도 조회하여 프론트엔드가 클라이언트에서 시계열에 오버레이한다. 시계열 엔드포인트 응답에 이벤트 데이터를 포함하지 않는다.

### 공통 사항

| 항목 | 값 |
|---|---|
| Base URL | `/api/v1` |
| 인증 | 없음 (1차 출시 범위 외) |
| 응답 형식 | `application/json` |
| 날짜 형식 | `YYYY-MM` (월 단위 표기 통일) |
| 에러 형식 | `{"error": {"code": "...", "message": "...", "context": {...}}}` |
| HTTP 상태 코드 | 200 성공 / 400 잘못된 파라미터 / 404 리소스 없음 / 500 서버 오류 |

**날짜 직렬화 방침 (D-11)**: 백엔드 Pydantic 시리얼라이저가 DB `DATE` 타입을 `YYYY-MM` 문자열로 포맷팅하여 응답한다 (`strftime("%Y-%m")`). Pydantic 필드 타입은 `str` + `field_validator`로 `YYYY-MM` 형식을 강제한다. 단, 타임스탬프(`last_updated` 등)는 ISO 8601 형식(`YYYY-MM-DDTHH:MM:SSZ`)으로 반환한다.

**에러 envelope (D-20)**: `context` 옵셔널 객체 필드로 추가 디버깅 정보(검증 실패 필드명, 추적 ID 등)를 포함할 수 있다.

```json
{
  "error": {
    "code": "INVALID_SEGMENT",
    "message": "3구간 품목에 존재하지 않는 구간 C를 요청했습니다.",
    "context": {
      "commodity_id": "wheat",
      "requested_segment": "C",
      "available_segments": ["A", "B", "D_prime"]
    }
  }
}
```

---

### 시계열 공통 쿼리 파라미터

시계열을 반환하는 모든 엔드포인트(`/stream`, `/scatter`, `/raw-prices`, `/stat-series`)에 공통 적용한다.

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `from` | `YYYY-MM` | — | 품목별 `analysis_start` | 조회 시작 월 (inclusive) |
| `to` | `YYYY-MM` | — | 최신 데이터 기준 월 | 조회 종료 월 (inclusive) |
| `granularity` | string | — | `"monthly"` | 집계 단위. `"monthly"` \| `"quarterly"` \| `"yearly"` |

**`granularity` 동작 규칙**

| 값 | 집계 단위 | 대표값 기준 | 주 사용처 |
|---|---|---|---|
| `monthly` | 월 1개 → 1 포인트 | 원본값 그대로 | 3년 이하 기간, 인라인 그래프 |
| `quarterly` | 3개월 평균 → 1 포인트 | 분기 마지막 월 기준 | 5년 기간 |
| `yearly` | 12개월 평균 → 1 포인트 | 연도 12월 기준 | 전체 기간, 미니맵 |

- `granularity` 값에 무관하게 **이상 노드는 항상 원본 월 단위로 반환**한다. 집계 포인트에 이상이 포함되면 해당 포인트에 `has_anomaly: true`와 `anomaly_ids` 배열을 함께 포함한다.
- `from`/`to` 범위 내에 데이터가 없는 월은 응답에서 생략한다 (null 포인트 미포함). 프론트엔드는 `total_points`로 연속성을 판단한다.

### 시계열 응답 공통 envelope

시계열 응답은 항상 아래 최상위 필드를 포함한다.

```json
{
  "requested_from": "2023-04",
  "requested_to":   "2026-03",
  "actual_from":    "2023-04",
  "actual_to":      "2026-03",
  "granularity":    "monthly",
  "total_points":   36,
  /* 엔드포인트별 데이터 필드 */
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `requested_from` / `requested_to` | `YYYY-MM` | 클라이언트가 요청한 범위 |
| `actual_from` / `actual_to` | `YYYY-MM` | 서버가 실제로 반환한 범위 (데이터 부재 시 클램핑) |
| `granularity` | string | 실제 적용된 집계 단위 |
| `total_points` | integer | 반환된 시계열 포인트 수 (구간·소스 구분 없이 단일 기간 기준) |

---

## 엔드포인트 목록

| 그룹 | 메서드 | 경로 | 설명 |
|---|---|---|---|
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
| 시각화 | GET | `/commodities/{commodity_id}/raw-prices/minimap` | 원시 시계열 미니맵 전용 |
| 패널 | GET | `/anomalies/{anomaly_id}/detail` | 분석 수치 패널 전체 (통계·ML·판정경로 통합) |
| 패널 | GET | `/anomalies/{anomaly_id}/stat-series` | 패널 내 지표별 인라인 시계열 |
| 패널 | GET | `/anomalies/{anomaly_id}/stat-snapshot` | 비시계열 지표 스냅샷 (IQR 박스플롯·비대칭 히스토그램) |
| 패널 | GET | `/anomalies/{anomaly_id}/irf` | IRF 차트 데이터 |
| 패널 | GET | `/anomalies/{anomaly_id}/ml-map` | ML 결과맵 2D 투영 데이터 |
| 방법론 | GET | `/meta/pipeline` | 파이프라인 플로우 데이터 (정적) |
| 방법론 | GET | `/meta/analysis-params` | 파이프라인 파라미터 기준값 (정적) |

---

## 참조 엔드포인트

### `GET /commodities` — 품목 목록

품목 선택 드롭다운(web_plan_v6 §3.3) 및 초기 데이터 로드. 이달 이상 여부 배지 포함.

**쿼리 파라미터**: 없음

**응답**

```json
{
  "commodities": [
    {
      "commodity_id": "wheat",
      "name_kr": "밀",
      "name_en": "Wheat",
      "cluster": "grain",
      "has_wholesale": false,
      "route_type": "3seg",
      "segments": ["A", "B", "D_prime"],
      "analysis_start": "2000-01",
      "analysis_end": "2026-03",
      "has_anomaly_this_month": true,
      "latest_anomaly_grade": "high"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `commodity_id` | string | 품목 식별자 |
| `name_kr` / `name_en` | string | 품목명 |
| `cluster` | string | `grain` \| `oil_sugar` \| `tropical` \| `livestock` \| `independent` |
| `has_wholesale` | boolean | 도매가 데이터 존재 여부 |
| `route_type` | string | `"3seg"` \| `"4seg"` |
| `segments` | string[] | 분석 구간 목록 |
| `analysis_start` / `analysis_end` | `YYYY-MM` | 품목별 분석 가용 범위 |
| `has_anomaly_this_month` | boolean | 이번 달 이상 탐지 여부 (드롭다운 배지용) |
| `latest_anomaly_grade` | string \| null | 이번 달 최고 신뢰도 등급 (`"high"` \| `"medium"` \| `"reference"` \| null) |

---

### `GET /commodities/{commodity_id}` — 단일 품목 상세

`/commodities` 응답에 구간별 모형 유형·기준선을 추가한 확장 응답. 품목 전환 시 호출.

**응답** — `/commodities` 단일 품목 필드 + `segment_meta` 추가

```json
{
  "commodity_id": "wheat",
  "segment_meta": {
    "A": {
      "model_type": "VECM",
      "cointegrated": true,
      "normal_transmission_lag": 2,
      "transmission_elasticity": 0.72,
      "upstream_label": "국제가 (원화 환산)",
      "downstream_label": "수입단가",
      "warmup_end": "2003-12"
    },
    "B": {
      "model_type": "VAR",
      "cointegrated": false,
      "normal_transmission_lag": 1,
      "transmission_elasticity": 0.58,
      "upstream_label": "수입단가",
      "downstream_label": "PPI",
      "warmup_end": "2003-12"
    }
  }
}
```

**기준선 선택 규칙 (D-15)**: `segment_meta`의 `normal_transmission_lag`·`transmission_elasticity`·`warmup_end`는 **전체 기간 기준선** (`baselines.subperiod_id IS NULL`)을 반환한다. 하위 기간별 기준선은 `/anomalies/{id}/irf` 엔드포인트를 통해서만 노출한다.

**`warmup_end` 출처 (D-06)**: `baselines.warmup_end` 컬럼에서 직접 반환한다. 별도 집계 쿼리 없음.

| 추가 필드 | 타입 | 설명 |
|---|---|---|
| `segment_meta.{seg}.warmup_end` | `YYYY-MM` | 롤링 윈도우 48개월 축적 완료 시점. 이 월까지는 탐지 결과 없음 |

---

### `GET /segments` — 분석 구간 정의 목록

```json
{
  "segments": [
    {
      "segment_id": "A",
      "label_kr": "구간 A (국제가→수입단가)",
      "upstream_label": "국제가 (원화 환산)",
      "downstream_label": "수입단가",
      "applies_to": "all",
      "pattern1": true,
      "pattern2": true,
      "pattern3": false,
      "ml_applied": true
    }
  ]
}
```

---

### `GET /events` — 외부 충격 이벤트 목록

사건 필터 드롭다운(web_plan_v6 §3.4) 데이터 소스. 프론트엔드가 이 목록을 사용하여 시계열 그래프에 배경 음영을 오버레이한다.

```json
{
  "events": [
    {
      "event_key": "ukraine_2022",
      "label_kr": "2022 우크라이나 사태",
      "start_date": "2022-02",
      "end_date": "2022-10",
      "color_hex": "#EF4444"
    }
  ]
}
```

---

### `GET /freshness` — 데이터 기준 시점

상단 바 칩 컴포넌트(web_plan_v6 §3.3) 데이터 소스.

```json
{
  "data_up_to": "2026-03",
  "next_run_date": "2026-04-15",
  "last_updated": "2026-04-01T03:00:00Z"
}
```

---

## 요약 엔드포인트

### `GET /anomalies/summary` — 이달의 이상 요약 배너

이달의 이상 요약 배너(web_plan_v6 §3.2) 데이터 소스.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `grade` | string | — | `"high,medium"` | 등급 필터. 콤마 구분 복수 지정 |
| `month` | `YYYY-MM` | — | 최신 기준 월 | 기준 월 명시 (이전 달 조회 가능) |

**응답**

```json
{
  "reference_month": "2026-03",
  "total_count": 5,
  "prev_month_count": 3,
  "count_diff": 2,
  "anomalies": [
    {
      "anomaly_id": 142,
      "commodity_id": "wheat",
      "commodity_name_kr": "밀",
      "segment_id": "A",
      "period": "2026-03",
      "primary_pattern": "pattern2",
      "confidence_grade": "high",
      "is_new": true,
      "transmission_rate": 1.43
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `reference_month` | `YYYY-MM` | 기준 월 |
| `total_count` | integer | 기준 월 탐지 건수 (행 수 기준, 동월 복수 패턴은 1건) |
| `prev_month_count` | integer | 직전 월 탐지 건수 |
| `count_diff` | integer | 증감 (양수 = 증가) |
| `anomalies[].anomaly_id` | integer | 패널 진입 키 |
| `anomalies[].is_new` | boolean | 이번 배치 신규 탐지 여부 (NEW 배지) |

---

## 시각화 엔드포인트

### `GET /commodities/{commodity_id}/stream` — 스트림 그래프

스트림 그래프(web_plan_v6 §4.1)의 전이율 시계열 + 이상 노드. 보조 품목 오버레이 시 동일 엔드포인트를 두 번 호출한다.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `from` | `YYYY-MM` | — | `analysis_start` | 조회 시작 월 |
| `to` | `YYYY-MM` | — | 최신 기준 월 | 조회 종료 월 |
| `granularity` | string | — | `"monthly"` | 집계 단위 |
| `segments` | string | — | 품목 전체 구간 | 구간 필터. 콤마 구분 (`A,B,D_prime`) |
| `grade` | string | — | `"high,medium"` | 이상 노드 신뢰도 필터 |
| `patterns` | string | — | `"pattern1,pattern2,pattern3"` | 패턴 필터 |

**응답**

```json
{
  "commodity_id": "wheat",
  "requested_from": "2023-04",
  "requested_to":   "2026-03",
  "actual_from":    "2023-04",
  "actual_to":      "2026-03",
  "granularity":    "monthly",
  "total_points":   36,
  "series": [
    {
      "segment_id": "A",
      "data": [
        {
          "period": "2023-04",
          "transmission_rate": 0.92,
          "upstream_pct": 5.1,
          "downstream_pct": 4.7,
          "in_warmup_period": false,
          "has_anomaly": false,
          "anomaly_ids": []
        },
        {
          "period": "2026-03",
          "transmission_rate": 1.43,
          "upstream_pct": 18.2,
          "downstream_pct": 26.1,
          "in_warmup_period": false,
          "has_anomaly": true,
          "anomaly_ids": [142]
        }
      ]
    }
  ],
  "anomaly_nodes": [
    {
      "anomaly_id": 142,
      "segment_id": "A",
      "period": "2026-03",
      "primary_pattern": "pattern2",
      "pattern_types": ["pattern2"],
      "confidence_grade": "high",
      "transmission_rate": 1.43,
      "is_new": true
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `series[].data[].transmission_rate` | number \| null | 전이율 직접값 (스트림 그래프 Y축) |
| `series[].data[].in_warmup_period` | boolean | 롤링 윈도우 축적 기간 여부 (곡선 표시 제어용) |
| `series[].data[].has_anomaly` | boolean | 해당 포인트에 이상 포함 여부 |
| `series[].data[].anomaly_ids` | integer[] | 포함된 이상 결과 ID 목록 |
| `anomaly_nodes` | array | 이상 노드 목록. **`granularity`에 무관하게 항상 원본 월 단위로 반환** |
| `anomaly_nodes[].anomaly_id` | integer | 패널 진입 키 — 클릭 시 `/anomalies/{anomaly_id}/detail` 호출 |

---

### `GET /commodities/{commodity_id}/stream/minimap` — 스트림 미니맵

미니맵(web_plan_v6 §4.1) 전용 엔드포인트. 항상 전체 기간을 `granularity=yearly`로 압축하여 반환한다.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `segments` | string | — | 품목 전체 구간 | 구간 필터 |

**응답** — `/stream` 응답 구조 + 아래 고정값 + `anomaly_density` 추가

```json
{
  "commodity_id": "wheat",
  "requested_from": "2000-01",
  "requested_to":   "2026-03",
  "actual_from":    "2000-01",
  "actual_to":      "2026-03",
  "granularity":    "yearly",
  "total_points":   26,
  "series": [ /* 연별 집계 전이율 */ ],
  "anomaly_density": [
    {
      "period": "2022",
      "high_count": 3,
      "medium_count": 1,
      "reference_count": 0
    }
  ]
}
```

`anomaly_density` 데이터 소스는 `mv_anomaly_density_yearly` 머티리얼라이즈드 뷰에서 조회한다.

| 추가 필드 | 타입 | 설명 |
|---|---|---|
| `anomaly_density` | array | 연도별 신뢰도 등급별 이상 건수 |

---

### `GET /commodities/{commodity_id}/scatter` — 전달 구조 산점도

전달 구조 뷰(web_plan_v6 §4.2)의 연결 산점도. 산점도는 항상 월 단위 원본값을 사용한다.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `segment` | string | **필수** | — | 단일 구간 지정 (`A`, `B`, `C`, `D`, `D_prime`) |
| `from` | `YYYY-MM` | — | `analysis_start` | 조회 시작 월 |
| `to` | `YYYY-MM` | — | 최신 기준 월 | 조회 종료 월 |
| `grade` | string | — | `"high,medium"` | 이상 노드 신뢰도 필터 |
| `until` | `YYYY-MM` | — | — | 슬라이더 재생 시 궤적 표시 상한 |

**응답**

```json
{
  "commodity_id": "wheat",
  "segment_id": "A",
  "upstream_label": "국제가 (원화 환산)",
  "downstream_label": "수입단가",
  "requested_from": "2020-01",
  "requested_to":   "2026-03",
  "actual_from":    "2020-01",
  "actual_to":      "2026-03",
  "granularity":    "monthly",
  "total_points":   75,
  "until":          "2026-03",
  "baseline": {
    "transmission_elasticity": 0.72,
    "normal_transmission_lag": 2
  },
  "points": [
    {
      "period": "2022-03",
      "upstream_pct": 18.2,
      "downstream_pct": 26.1,
      "is_anomaly": true,
      "anomaly_id": 142,
      "confidence_grade": "high",
      "primary_pattern": "pattern2"
    }
  ]
}
```

---

### `GET /commodities/{commodity_id}/raw-prices` — 원시 시계열

원시 시계열 뷰(web_plan_v6 §4.3). 레이아웃 파라미터로 포함 소스·구간 조합을 결정한다.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `layout` | integer | — | `1` | 레이아웃 번호 (1~6) |
| `from` | `YYYY-MM` | — | `analysis_start` | 조회 시작 월 |
| `to` | `YYYY-MM` | — | 최신 기준 월 | 조회 종료 월 |
| `granularity` | string | — | `"monthly"` | 집계 단위 |

**레이아웃별 포함 소스 및 폴백 정책 (D-12)**

| 레이아웃 | 4구간 품목 포함 소스 | 3구간 품목 포함 소스 | 에러 조건 |
|---|---|---|---|
| 1 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |
| 2 | intl·import | intl·import | — |
| 3 | import·ppi | import·ppi | — |
| 4 | ppi·wholesale | — | `WHOLESALE_NOT_AVAILABLE` (3구간 품목은 구간 C 자체가 없음) |
| 5 | wholesale·cpi (구간 D) | ppi·cpi (구간 D′, 자동 폴백) | 에러 없음. 3구간 품목에서 PPI-CPI로 자동 폴백 |
| 6 | intl·import·ppi·wholesale·cpi | intl·import·ppi·cpi | — |

**레이아웃 5 폴백 규칙 (D-12 확정)**: 3구간 품목에 레이아웃 5를 요청하면 도매가 대신 PPI를 상류로 사용하여 PPI-CPI(구간 D′)를 자동 표시한다. 에러를 반환하지 않는다. 레이아웃 4만 `WHOLESALE_NOT_AVAILABLE` 에러를 반환한다.

**응답**

```json
{
  "commodity_id": "wheat",
  "layout": 2,
  "requested_from": "2023-04",
  "requested_to":   "2026-03",
  "actual_from":    "2023-04",
  "actual_to":      "2026-03",
  "granularity":    "monthly",
  "total_points":   36,
  "series": [
    {
      "source": "intl_price_krw",
      "label_kr": "국제가 (원화 환산)",
      "color_hint": "purple",
      "data": [
        {
          "period": "2023-04",
          "value": 289.3,
          "index_2020": 137.5,
          "has_anomaly": false,
          "anomaly_ids": []
        }
      ]
    }
  ],
  "transmission_overlay": [
    {
      "segment_id": "A",
      "data": [
        {
          "period": "2023-04",
          "transmission_rate": 0.89,
          "has_anomaly": false,
          "anomaly_ids": []
        }
      ]
    }
  ],
  "anomaly_nodes": [
    {
      "anomaly_id": 142,
      "segment_id": "A",
      "period": "2026-03",
      "confidence_grade": "high",
      "primary_pattern": "pattern2",
      "is_new": true
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `series[].source` | string | 소스 컬럼명 |
| `series[].data[].index_2020` | number | 2020=100 기준 지수값 (Y축) |
| `transmission_overlay` | array | 레이아웃 2~6에서만 포함. 레이아웃 1은 빈 배열 |
| `anomaly_nodes` | array | **granularity 무관, 항상 원본 월 단위** |

---

### `GET /commodities/{commodity_id}/raw-prices/minimap` — 원시 시계열 미니맵

원시 시계열 뷰 미니맵 전용. 항상 전체 기간 `granularity=yearly`.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `layout` | integer | — | `1` | 레이아웃 번호 (소스 조합 결정용) |

**응답** — `/raw-prices` 응답과 동일한 구조. `granularity=yearly` 고정, `anomaly_density` 추가.

---

## 패널 엔드포인트

### `GET /anomalies/{anomaly_id}/detail` — 분석 수치 패널 통합

분석 수치 패널(web_plan_v6 §6) 초기 렌더링. 통계 수치·ML 판정 요약·패턴 판정 경로를 단일 요청으로 반환. IRF·지표 인라인 시계열·ML 결과맵·비시계열 지표 스냅샷은 별도 엔드포인트로 지연 로드.

**`judgment_path` 생성 주체 (D-04)**: 백엔드 API가 `anomaly_results`·`stat_timeseries`·`ml_scores` 등 여러 테이블을 조합하여 패턴 유형별 템플릿에 따라 동적으로 생성한다. 파이프라인이나 프론트엔드가 아닌 백엔드에서 생성한다.

**패턴별 `judgment_path` 템플릿 (D-04)**

| 패턴 | step 1 | step 2 | step 3 | step 4 | step 5 | step 6 |
|---|---|---|---|---|---|---|
| 패턴 1 단독 | 전이율 산출 | 방향 확인 | 시차 경과 확인 | 방향 역전/시차 이탈 판정 | ML 탐지 | 신뢰도 등급 확정 |
| 패턴 2 단독 | 전이율 산출 | 롤링 Z-score | IQR 판정 | 두 기준 동시 충족 | ML 탐지 | 신뢰도 등급 확정 |
| 패턴 3 단독 | 국제가 안정 구간 진입 | 스프레드 산출 | N개월 누적 확대 확인 | 탐지 확정 | ML 탐지 (A·B만) | 신뢰도 등급 확정 |
| 복수 패턴 | 각 패턴 판정 | 각 패턴 판정 | 각 패턴 판정 | 복수 탐지 확정 | ML 탐지 | 신뢰도 등급 확정 |

복수 패턴의 경우 `pattern_types` 배열 순서대로 각 step에서 패턴별 결과를 병렬 표기한다.

**응답**

```json
{
  "anomaly_id": 142,
  "commodity_id": "wheat",
  "commodity_name_kr": "밀",
  "segment_id": "A",
  "segment_label_kr": "구간 A (국제가→수입단가)",
  "period": "2026-03",
  "primary_pattern": "pattern2",
  "pattern_types": ["pattern2"],
  "confidence_grade": "high",
  "is_new": true,

  "stat_metrics": {
    "transmission_rate": 1.43,
    "rolling_mean": 0.81,
    "zscore": 2.71,
    "zscore_warning": true,
    "zscore_alert": true,
    "zscore_threshold_warning": 2.0,
    "zscore_threshold_alert": 2.5,
    "q1": 0.52,
    "q3": 1.09,
    "iqr_lower": 0.35,
    "iqr_upper": 1.26,
    "iqr_outlier": true,
    "over_transmission": true,
    "under_transmission": false,
    "normal_lag": 2,
    "actual_lag": null,
    "direction_reversal": false,
    "lag_deviation": false,
    "pattern1_flag_type": null,
    "ect_or_spread": 0.043,
    "ect_type": "ECT",
    "spread_n3": 0.021,
    "alpha_plus": -0.31,
    "alpha_minus": -0.09,
    "wald_pvalue": 0.003,
    "asymmetry_significant": true,
    "rocket_feather_direction": "upward_stronger",
    "model_type": "VECM",
    "cointegrated": true,
    "subperiod_index": 2,
    "bp_dates": ["2008-09", "2022-03"]
  },

  "ml_summary": {
    "ml_vote": 2,
    "ml_detected": true,
    "if_anomaly": true,
    "if_score": -0.142,
    "if_percentile": 96.3,
    "lof_anomaly": true,
    "lof_score": 2.81,
    "lof_percentile": 94.1,
    "svm_anomaly": false,
    "svm_score": 0.034,
    "svm_percentile": 62.0
  },

  "judgment_path": [
    { "step": 1, "label": "전이율 산출",       "value": "해당 월 전이율 = 1.43",          "passed": true },
    { "step": 2, "label": "롤링 Z-score",      "value": "2.71 → 경보 기준(2.5) 초과",     "passed": true },
    { "step": 3, "label": "IQR 판정",          "value": "Q3 + 1.5×IQR 상한(1.26) 초과",  "passed": true },
    { "step": 4, "label": "두 기준 동시 충족", "value": "통계 경보 확정",                  "passed": true },
    { "step": 5, "label": "ML 탐지",           "value": "IF ✓ / LOF ✓ / SVM ✗",          "passed": true },
    { "step": 6, "label": "신뢰도 등급 확정",  "value": "통계 O + ML 동시 확인 → 고신뢰", "passed": true }
  ]
}
```

**`stat_metrics` 신규 필드 (D-03)**

| 필드 | 타입 | 설명 |
|---|---|---|
| `zscore_warning` | boolean | 해당 월 Z-score > 2.0 여부 (DB `anomaly_results.zscore_warning`에서 반환) |
| `zscore_alert` | boolean | 해당 월 Z-score > 2.5 여부 |
| `zscore_threshold_warning` | number | 주의 임계값 상수 (2.0) |
| `zscore_threshold_alert` | number | 경보 임계값 상수 (2.5) |
| `pattern1_flag_type` | string \| null | `"direction_reversal"` \| `"lag_deviation"` \| `"both"` \| null (패턴 1 미탐지 시) |

**`stat_metrics` 필드 적용 구간**

| 필드 | 적용 구간 | 설명 |
|---|---|---|
| `transmission_rate`, `rolling_mean`, `zscore`, `zscore_warning`, `zscore_alert`, `iqr_*`, `over/under_transmission` | A·B | 패턴 2 전이율·Z-score·IQR 관련 |
| `normal_lag`, `actual_lag`, `direction_reversal`, `lag_deviation`, `pattern1_flag_type` | 전 구간 | 패턴 1 방향·시차 관련 |
| `ect_or_spread`, `ect_type` | 전 구간 | ECT / 로그 수준 스프레드 |
| `spread_n3` | B | 패턴 3 N=3 누적 스프레드 |
| `alpha_plus`, `alpha_minus`, `wald_pvalue`, `asymmetry_significant`, `rocket_feather_direction` | A·B (전체 기간 기준선) | TECM 비대칭 검정 |
| `model_type`, `cointegrated` | 전 구간 | 모형 유형 |
| `subperiod_index`, `bp_dates` | 전 구간 | 구조 변화·하위 기간 정보 |

---

### `GET /anomalies/{anomaly_id}/stat-series` — 지표별 인라인 시계열

패널 §계량경제학 수치 항목 클릭 시 펼쳐지는 시계열 그래프(web_plan_v6 §6.2). **시계열 형태인 지표만 처리**. 비시계열 지표(IQR 박스플롯, 비대칭 히스토그램)는 `/stat-snapshot` 참조.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `metric` | string | **필수** | — | 지표 종류 (아래 표) |
| `from` | `YYYY-MM` | — | `analysis_start` | 조회 시작 월 |
| `to` | `YYYY-MM` | — | 최신 기준 월 | 조회 종료 월 |
| `granularity` | string | — | `"monthly"` | 집계 단위 |

**`metric` 값 목록 (시계열 전용)**

| `metric` 값 | 그래프 내용 | 비고 |
|---|---|---|
| `transmission_rate` | 전이율 시계열 + 롤링 평균선 + Q1~Q3 정상 범위 밴드 + 탐지 시점 수직선 | |
| `zscore` | Z-score 시계열 + 주의(2.0)·경보(2.5) 수평 임계선 | |
| `ect` | ECT 또는 로그 수준 스프레드 시계열 + 기준선(0) | |
| `breakpoints` | 전이율 시계열 + 구조 변화 시점 수직선 | `transmission_rate`와 응답 구조 공유. `bp_dates` 추가 |

**`metric=breakpoints` 구조 변화 시점 출처 (D-16 수정)**: `breakpoints.bp_dates` (DATE[]) 컬럼에서 조회한다. `baselines.bp_dates`는 오기였으며 이를 수정한다.

**응답 (공통 envelope)**

```json
{
  "anomaly_id": 142,
  "commodity_id": "wheat",
  "segment_id": "A",
  "metric": "transmission_rate",
  "highlight_period": "2026-03",
  "requested_from": "2000-01",
  "requested_to":   "2026-03",
  "actual_from":    "2000-01",
  "actual_to":      "2026-03",
  "granularity":    "monthly",
  "total_points":   314,
  "data": [ /* metric별 상이, 아래 참조 */ ]
}
```

**`metric=transmission_rate` 및 `breakpoints` data 항목**

```json
{
  "period": "2022-03",
  "transmission_rate": 1.43,
  "rolling_mean": 0.81,
  "q1": 0.52,
  "q3": 1.09,
  "in_warmup_period": false,
  "is_breakpoint": false
}
```

**`metric=zscore` data 항목**

```json
{
  "period": "2022-03",
  "zscore": 2.71,
  "in_warmup_period": false
}
```

**`metric=ect` data 항목**

```json
{
  "period": "2022-03",
  "ect_or_spread": 0.043,
  "ect_type": "ECT"
}
```

---

### `GET /anomalies/{anomaly_id}/stat-snapshot` — 비시계열 지표 스냅샷

패널 내 **시계열이 아닌** 지표의 정적 스냅샷. `from`/`to`/`granularity` 파라미터 불필요.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `metric` | string | **필수** | `"iqr"` \| `"asymmetry"` |

**응답 — `metric=iqr`** (롤링 48개월 기준 해당 시점 분포)

```json
{
  "anomaly_id": 142,
  "metric": "iqr",
  "period": "2026-03",
  "q1": 0.52,
  "median": 0.81,
  "q3": 1.09,
  "iqr_lower": 0.35,
  "iqr_upper": 1.26,
  "current_value": 1.43,
  "window_months": 48
}
```

**응답 — `metric=asymmetry`** (상승기/하락기 전이율 분포 히스토그램용)

```json
{
  "anomaly_id": 142,
  "metric": "asymmetry",
  "model_type": "TECM",
  "up_samples": [0.92, 1.12, 1.43, 1.21],
  "down_samples": [0.43, 0.61, 0.55, 0.48],
  "alpha_plus": -0.31,
  "alpha_minus": -0.09,
  "wald_pvalue": 0.003,
  "asymmetry_significant": true
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `up_samples` | number[] | 상승 국면 전이율 관측치 목록 (히스토그램 데이터) |
| `down_samples` | number[] | 하락 국면 전이율 관측치 목록 |

---

### `GET /anomalies/{anomaly_id}/irf` — IRF 차트

패널 §IRF 차트(web_plan_v6 §6.5). 전체 기간 베이스라인 + 하위 기간별 IRF 곡선.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `include_subperiods` | boolean | — | `true` | 하위 기간별 IRF 포함 여부 |

**응답**

```json
{
  "commodity_id": "wheat",
  "segment_id": "A",
  "irfs": [
    {
      "scope": "full",
      "label": "전체 기간",
      "estimation_start": "2000-01",
      "estimation_end": "2026-03",
      "peak_horizon": 2,
      "peak_magnitude": 0.72,
      "data": [
        { "horizon": 0, "irf_downstream": 0.0,  "irf_lower_ci": -0.02, "irf_upper_ci": 0.02 },
        { "horizon": 1, "irf_downstream": 0.41, "irf_lower_ci": 0.28,  "irf_upper_ci": 0.54 },
        { "horizon": 2, "irf_downstream": 0.72, "irf_lower_ci": 0.58,  "irf_upper_ci": 0.86 }
      ]
    },
    {
      "scope": "subperiod",
      "subperiod_index": 2,
      "label": "2008-10 ~ 2022-02",
      "estimation_start": "2008-10",
      "estimation_end": "2022-02",
      "peak_horizon": 1,
      "peak_magnitude": 0.89,
      "data": [ /* 동일 구조 */ ]
    }
  ]
}
```

---

### `GET /anomalies/{anomaly_id}/ml-map` — ML 결과맵 투영 데이터

패널 §ML 결과맵(web_plan_v6 §6.3). 모델별 파라미터 분기.

> **OI-15 보류**: `projection_method` 기본값 및 축 확정은 S4 스프린트 내.

**쿼리 파라미터**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|:---:|---|---|
| `model` | string | **필수** | — | `"isolation_forest"` \| `"lof"` \| `"ocsvm"` |
| `projection_method` | string | — | `"pca"` | `"pca"` \| `"feature_direct"` |

**응답**

```json
{
  "anomaly_id": 142,
  "commodity_id": "wheat",
  "segment_id": "A",
  "model": "isolation_forest",
  "projection_method": "pca",
  "x_label": "PC1",
  "y_label": "PC2",
  "total_points": 314,
  "points": [
    {
      "period": "2022-03",
      "x_value": 1.23,
      "y_value": -0.45,
      "anomaly_score": -0.142,
      "is_anomaly": true,
      "is_highlight": true
    }
  ]
}
```

---

## 방법론 엔드포인트

정적 데이터. `ETag` + `Cache-Control: max-age=86400` 헤더를 포함한다.

### `GET /meta/pipeline` — 파이프라인 플로우

방법론 탭 §섹션 1(web_plan_v6 §8.2). D3.js가 직접 소비하는 노드-엣지 형식.

**응답**

```json
{
  "version": "v8",
  "nodes": [
    { "id": "phase0",     "label": "Phase 0",    "description": "데이터 수집·전처리",   "phase_number": 0 },
    { "id": "phase1",     "label": "Phase 1",    "description": "계절 조정 (STL)",      "phase_number": 1 },
    { "id": "phase2",     "label": "Phase 2",    "description": "정상성 검정",           "phase_number": 2 },
    { "id": "phase3",     "label": "Phase 3",    "description": "공적분 검정",           "phase_number": 3 },
    { "id": "phase4_vecm","label": "VECM 추정",  "description": "장기 균형 포함 모형",  "phase_number": 4 },
    { "id": "phase4_var", "label": "VAR 추정",   "description": "단기 동적 모형",       "phase_number": 4 },
    { "id": "phase5",     "label": "Phase 5",    "description": "Granger 인과 검정",    "phase_number": 5 },
    { "id": "phase6",     "label": "Phase 6",    "description": "구조 변화 탐지",       "phase_number": 6 },
    { "id": "phase7",     "label": "Phase 7",    "description": "통계 기반 이상 탐지",  "phase_number": 7 },
    { "id": "phase7_ml",  "label": "Phase 7-ML", "description": "ML 보조 교차검증",     "phase_number": 7.5 },
    { "id": "phase8",     "label": "Phase 8",    "description": "결과 종합·등급화",     "phase_number": 8 }
  ],
  "edges": [
    { "source": "phase0",     "target": "phase1" },
    { "source": "phase1",     "target": "phase2" },
    { "source": "phase2",     "target": "phase3" },
    { "source": "phase3",     "target": "phase4_vecm", "label": "공적분 있음" },
    { "source": "phase3",     "target": "phase4_var",  "label": "공적분 없음" },
    { "source": "phase4_vecm","target": "phase5" },
    { "source": "phase4_var", "target": "phase5" },
    { "source": "phase5",     "target": "phase6" },
    { "source": "phase6",     "target": "phase7" },
    { "source": "phase6",     "target": "phase7_ml" },
    { "source": "phase7",     "target": "phase8" },
    { "source": "phase7_ml",  "target": "phase8" }
  ]
}
```

---

### `GET /meta/analysis-params` — 파이프라인 파라미터 기준값

방법론 탭 §섹션 2·3(web_plan_v6 §8.2).

**응답**

```json
{
  "version": "v8",
  "params": {
    "rolling_window": 48,
    "zscore_warning": 2.0,
    "zscore_alert": 2.5,
    "iqr_multiplier": 1.5,
    "stability_threshold": 0.03,
    "pattern3_n_values": [2, 3, 6],
    "min_subperiod_obs": 60,
    "lag_search_range": [1, 4], // Phase 3 AIC 탐색 범위; Phase 4는 Phase 3 결정값을 전달받아 사용
    "chow_test_points": ["2008-01", "2020-01", "2022-01"]
  },
  "patterns": [
    {
      "pattern_id": "pattern1",
      "label_kr": "패턴 1: 방향 역전 및 시차 이탈",
      "description": "국제 원자재 가격이 변동할 때 다음 단계 가격이 반대 방향으로 움직이거나, 정상 전달 시차(IRF 피크 시점 + 버퍼 1개월)를 초과해도 하류가 무반응인 경우",
      "applicable_segments": ["A", "B", "C", "D", "D_prime"]
    },
    {
      "pattern_id": "pattern2",
      "label_kr": "패턴 2: 전이율 크기 이탈 및 비대칭 전달(로켓-깃털 효과)",
      "description": "전이율이 롤링 Z-score와 IQR 기준을 동시 초과하거나, TECM/비대칭 VAR에서 상승·하락 조정 속도가 유의미하게 다른 경우",
      "applicable_segments": ["A", "B"]
    },
    {
      "pattern_id": "pattern3",
      "label_kr": "패턴 3: 국제가격 안정기 중 하류 물가 스프레드 누적 확대",
      "description": "국제가 안정기(원화 환산 월 변동 ±3% 이내)에 수입단가-PPI 간 수준 괴리가 N개월 연속 같은 방향으로 확대되는 경우",
      "applicable_segments": ["B"]
    }
  ]
}
```

---

## 에러 코드 정의

| HTTP 코드 | `error.code` | 발생 조건 |
|---|---|---|
| 400 | `INVALID_SEGMENT` | 해당 품목에 존재하지 않는 구간 지정 (예: 3구간 품목에 구간 C 요청) |
| 400 | `INVALID_METRIC` | `stat-series` / `stat-snapshot`에서 지원하지 않는 `metric` 값 |
| 400 | `INVALID_DATE_RANGE` | `from`이 `to`보다 이후이거나 분석 가용 범위 밖 |
| 400 | `INVALID_LAYOUT` | `raw-prices`에서 1~6 범위 밖 레이아웃 지정 |
| 400 | `WHOLESALE_NOT_AVAILABLE` | 3구간 품목에 **레이아웃 4** 요청 (레이아웃 5는 PPI-CPI로 자동 폴백하여 에러 아님, D-12) |
| 400 | `INVALID_GRANULARITY` | `granularity`에 `monthly` \| `quarterly` \| `yearly` 외 값 지정 |
| 400 | `UNTIL_EXCEEDS_TO` | `scatter`에서 `until`이 `to`보다 이후 |
| 400 | `SNAPSHOT_METRIC_ON_SERIES` | `/stat-series`에 `iqr` 또는 `asymmetry` 지정 (→ `/stat-snapshot` 안내) |
| 404 | `COMMODITY_NOT_FOUND` | 존재하지 않는 `commodity_id` |
| 404 | `ANOMALY_NOT_FOUND` | 존재하지 않는 `anomaly_id` |
| 404 | `ML_MAP_NOT_READY` | ML 결과맵 미산출 (파이프라인 미완료) |
| 404 | `WARMUP_PERIOD_ONLY` | 요청 범위 전체가 롤링 윈도우 축적 기간이어서 탐지 결과 없음 |
| 500 | `PIPELINE_DATA_MISSING` | 파이프라인 산출물 미적재 |

---

## 통합 판단 근거 요약

| 통합 대상 | 통합 방식 | 분리 검토 조건 |
|---|---|---|
| 패널 통계·ML·판정경로 | `/anomalies/{id}/detail` 단일 엔드포인트 | 패널 섹션별 lazy load가 필요해질 경우 분리 |
| 지표별 인라인 시계열 4종 | `/anomalies/{id}/stat-series?metric=` 파라미터 분기 | 지표별 응답 구조 차이가 너무 커질 경우 분리 |
| 비시계열 지표 2종 | `/anomalies/{id}/stat-snapshot?metric=` 파라미터 분기 | `iqr`과 `asymmetry`는 성격이 달라 분리 가능 |
| ML 결과맵 3모델 | `/anomalies/{id}/ml-map?model=` 파라미터 분기 | 모델별 투영 방식이 달라질 경우 분리 |
| 원시 시계열 레이아웃 6종 | `/commodities/{id}/raw-prices?layout=` 파라미터 분기 | 레이아웃별 쿼리 최적화가 필요해질 경우 분리 |
| `metric=breakpoints` | `transmission_rate` data에 `is_breakpoint` 필드 통합 (`breakpoints.bp_dates` 출처) | — |

---

## 미결 사항

| 번호 | 내용 | 결정 시점 |
|---|---|---|
| OI-15 연동 | `ml-map` `projection_method` 기본값 및 `x_label`/`y_label` 확정 | S4 |
| 캐시 키 규칙 | Redis TTL 및 캐시 무효화 전략 상세 (`pipeline_runs.id` 키 포함 방향 예비 기록) | S6 (백엔드 개발 착수 후) |
| `granularity=quarterly` 집계 기준 | 분기 대표값을 마지막 월 기준으로 할지 중앙값으로 할지 | S6 |
| minimap 재호출 조건 | 배치 갱신 이후 미니맵 캐시 무효화 트리거 명세 | S6 |

---

*v4 — pipeline_output_spec_v5 반영. Phase 3~7 미구현 구간 응답 필드는 pipeline_output_spec_v5 / db_schema_v2 기준 설계. 파이프라인 구현 완료 후 실제 출력과 대조하여 갱신 필요.*
