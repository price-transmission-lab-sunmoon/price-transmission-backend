# 백엔드 회신 합의서 (Backend-as-SoT) — price-transmission-backend → frontend

> 프론트 「백엔드 합의 계약서」 각 지점을 **백엔드 실제 코드·데이터와 verbatim 대조**한 확정 회신.
> **원칙: 백엔드 현 구현이 정본(SoT). 프론트가 이에 맞춤.** 각 항목 evidence = 실제 파일:라인.
> 작성 기준 커밋: `ed79246` (develop). 검증 방식: 코드 직접 확인 + `data/processed` 실측 샘플.

---

## 0. 한눈 요약 (FE 즉시 조치 필요 항목)

| 우선 | 항목 | 계약 기대 | 백엔드 실제(SoT) | FE 조치 |
|---|---|---|---|---|
| 🔴 | **M5 period(yearly)** | `YYYY` | **`YYYY-MM`(12월 고정)** 예 `2022-12` | yearly 파싱 로직 수정 |
| 🔴 | **public_code 위치** | 최상위 독립 필드 | `error.code`에 PUBLIC_CODE 삽입 | `error.code`에서 읽기 |
| 🟠 | **WHOLESALE_NOT_AVAILABLE** | 422 | **400** | status 분기 수정 |
| 🟠 | **SNAPSHOT_METRIC_ON_SERIES** | 422 | **400** | status 분기 수정 |
| 🟠 | **ML_MAP_NOT_READY** | 404 | **미구현** → 200 `points=[]` | `total_points==0` 분기 |
| 🟠 | **H1 transmission_rate** | ratio | **ratio(0.5)** 확정 / `*_pct`는 % | 혼용·×100 금지 |
| 🟡 | **M3 /stream from/to** | 금지 | **수신·처리됨**(기본 None) | 계약 문구 수정 |
| 🟡 | **UNTIL_EXCEEDS_TO** | until>to 기준 | **analysis_end 기준** | 검증 기준 변경 |

---

## 1. 에러 규약

### 1-1. 에러 envelope (★구조 변경)
- 실제 응답: `{"error":{"code":"<PUBLIC_CODE>","message":"...","context":{...}?}}`
- **독립 `public_code` 최상위 필드 없음.** `api_error_handler`가 `public_code`를 `error.code` 자리에 넣음.
- 근거: `app/core/exceptions.py:127-131`(`_error_body`), `:144-147`(`content=_error_body(exc.public_code, ...)`)
- **FE 합의**: `error.code`에서 public_code 값을 읽을 것. 최상위 `public_code` 필드 기대 금지. `error.code` 없으면 FE `PARSE-SCHEMA-001` 유지.

### 1-2. 공인 public_code 매핑 (내부코드 ↔ public_code ↔ HTTP)

| public_code | HTTP | 내부코드 | 발생 위치 | 판정 |
|---|---|---|---|---|
| `COMMODITY_NOT_FOUND` | 404 | API-COM-001 | reference.py:100 | ✅ 일치 |
| `ANOMALY_NOT_FOUND` | 404 | API-ANO-001 | anomaly_panel.py:58 | ✅ 일치 |
| `WARMUP_PERIOD_ONLY` | 404 | API-STR-001 | stream/raw_prices/scatter 공통 | ✅ 일치 |
| `INVALID_SEGMENT` | 400 | API-SEG-001 | stream/scatter | ✅ 일치 |
| `INVALID_GRANULARITY` | 400 | API-STR-004 / API-MET-001 | stream·raw_prices / panel | ✅ 일치 |
| `INVALID_DATE_RANGE` | 400 | API-STR-002/003, coerce | stream.py:49-70, coerce.py:53-81 | ✅ 일치 |
| `INVALID_METRIC` | 400 | API-MET-001 | anomaly_panel.py:266 | ✅ 일치 |
| `PIPELINE_DATA_MISSING` | **500** | API-COM-002 / API-ANO-002 | reference·panel·endpoint | ✅ 일치 |
| `INVALID_LAYOUT` | 400 | API-LAY-001 | raw_prices.py:66 | ✅ (단 Pydantic이 먼저 잡으면 `API-VAL-001`) |
| **`WHOLESALE_NOT_AVAILABLE`** | **400** (≠422) | API-LAY-002 | raw_prices.py:75 | ⚠️ status 불일치 |
| **`SNAPSHOT_METRIC_ON_SERIES`** | **400** (≠422) | API-MET-002 | anomaly_panel.py:258 | ⚠️ status 불일치 |
| **`UNTIL_EXCEEDS_TO`** | 400 | API-STR-005 | scatter.py:68-83 | ⚠️ 검증기준 다름(아래) |
| **`ML_MAP_NOT_READY`** | — | — | **미구현** | ❌ 200 빈응답으로 대체 |
| **`NOT_IMPLEMENTED`** | — | — | **미구현**(app 코드 미사용) | ❌ |

- **FE 합의**:
  - `WHOLESALE_NOT_AVAILABLE`·`SNAPSHOT_METRIC_ON_SERIES`는 **400**으로 처리(422 아님).
  - `INVALID_LAYOUT`: 서비스 코드(`INVALID_LAYOUT`)와 Pydantic 선검증(`API-VAL-001`) **두 코드 모두** 핸들.
  - `ML_MAP_NOT_READY`·`NOT_IMPLEMENTED`는 백엔드 미반환 → 기대 금지.

### 1-3. anomaly/summary grade 오류 (버그성 — 백엔드 차기 수정 예정)
- `parse_grades` invalid 시 `public_code="API-VAL-001"`로 설정됨(다른 곳은 의미코드 사용). 근거 `anomaly_summary.py:22-29`
- **FE 합의(잠정)**: 해당 오류는 `error.code=="API-VAL-001"` 조건으로 처리. (백엔드가 의미코드로 정정 시 재공지)

---

## 2. 스케일 · nullable · 타입

### H1. transmission_rate 스케일 — **비율(ratio)** 확정
- `transmission_rate` = **무차원 비율**. 실측 `0.9185`, `-0.0373`, `-1.0007` 등. 로더·서비스 전 구간 `*100`/`/100` 없음.
- `upstream_pct`·`downstream_pct` = **퍼센트(%)**. 실측 `-4.836`, `15.308` 등.
- 근거: `data/processed/phase7/stat_timeseries/banana_A_stat_timeseries.csv:3`, `phase7.py:117`, `stream.py:208`
- **FE 합의**: `transmission_rate`는 비율(1.0 기준)로 해석, **×100·% 표기 금지**(단위 없음 또는 '배율'). `*_pct`만 %.

### H2. transmission_rate nullable — **Optional 확정**
- `AnomalySummaryItem`/`StreamDataPoint`/`AnomalyNode` 모두 `transmission_rate: float | None = None`.
- 근거: `schemas/anomaly.py:30`, `schemas/timeseries.py:43`, `:69`
- **FE 합의**: 수신 시 항상 null 체크 후 렌더. SoT 타입 = `number | null`.

### H3. ml percentile — **0~100** 확정
- `_compute_percentiles`: `rank(pct=True, ascending=False) * 100`, 적재 `limit=100.0`.
- 근거: `phase7_ml.py:85`, `:129-135`
- **FE 합의**: percentile은 0~100. `/100` 가정(여정④)과 일치 — 0~1 비율로 처리 금지.

### H6. ml score·percentile null 조건
- null 조건: ① `ml_scores` 행 미존재(해당 period 데이터 없음) → 전부 None, ② 원값 NaN/Inf/|값|>9999.0 → None.
- **warmup 기반 null 게이트 없음**. (단 asymmetry 히스토그램 표본은 `in_warmup_period.is_(False)` 필터 — score null과 무관)
- 근거: `anomaly_panel.py:127-133`, `:177-183`, `phase7_ml.py:41-50`
- **FE 합의**: score/percentile null = 'N/A' 표시. warmup 여부와 분리 처리.

---

## 3. raw-prices (label_kr · charset · layout)

### C1. label_kr — 백엔드 `_SOURCE_META` 정본 (`raw_prices.py:32-38`)
| source | label_kr (정본) | color_hint |
|---|---|---|
| `intl_price_krw` | **국제가 (원화 환산)** | purple |
| `import_price_usd` | **수입단가** | orange |
| `ppi` | **생산자물가지수 (PPI)** | green |
| `cpi` | **소비자물가지수 (CPI)** | red |
| `wholesale_price` | **도매가격** | blue |
- **FE 합의**: RawPricesChart 탭은 위 label_kr을 **그대로 표시**(임의 재명명 금지).

### C1. charset — **정상 UTF-8** (fixture 문제)
- starlette `JSONResponse` 기본 `json.dumps(ensure_ascii=False).encode("utf-8")`. 오버라이드 없음.
- 근거: `commodities.py:156-189`, `main.py:100-104`
- **FE 합의**: 실응답은 `application/json; charset=utf-8` 정상. **fixture의 mojibake는 픽스처 인코딩 손상 문제** — 실서버 응답과 무관(별도 charset 협상 불필요).

### M4. layout 1~6 → source 매핑 (`raw_prices.py:41-57`)
**4구간 품목(`_LAYOUT_SOURCES_4SEG`)**
| layout | sources |
|---|---|
| 1 | intl_price_krw, import_price_usd, ppi, wholesale_price, cpi |
| 2 | intl_price_krw, import_price_usd |
| 3 | import_price_usd, ppi |
| 4 | ppi, wholesale_price |
| 5 | wholesale_price, cpi |
| 6 | (1과 동일 5개) |

**3구간 품목(`_LAYOUT_SOURCES_3SEG`)**
| layout | sources |
|---|---|
| 1 | intl_price_krw, import_price_usd, ppi, cpi |
| 2 | intl_price_krw, import_price_usd |
| 3 | import_price_usd, ppi |
| **4** | **에러 400 / `WHOLESALE_NOT_AVAILABLE`** |
| 5 | ppi, cpi (도매가 없이 PPI→CPI 폴백) |
| 6 | (1과 동일 4개) |

- `layout=1` → `transmission_overlay = []` (빈 배열, **null 아님**).
- 3구간+layout4 에러코드 = `WHOLESALE_NOT_AVAILABLE`(≠`INVALID_LAYOUT`).
- **FE 합의**: 소스 순서는 위 매핑대로 렌더. 3구간 품목은 layout 4 비활성화 권장, layout 5는 도매가 없이 표시됨을 UI 반영.

### M7. anomaly node 차이 (클래스명 정정 포함)
- stream 노드 클래스명 = **`AnomalyNode`** (계약의 `StreamAnomalyNode`는 코드에 없음).
- `AnomalyNode`(stream): anomaly_id, segment_id, period, primary_pattern, **pattern_types**, confidence_grade, **transmission_rate**, is_new
- `RawPriceAnomalyNode`(raw-prices): anomaly_id, segment_id, period, confidence_grade, primary_pattern, is_new → **pattern_types·transmission_rate 없음**
- 근거: `schemas/timeseries.py:62-69`, `:127-133`
- **FE 합의**: raw-prices의 anomaly_nodes에서 pattern_types·transmission_rate 참조 금지(둘은 /stream에만).

---

## 4. period 포맷 (★CRITICAL)

| 필드 | granularity | 백엔드 실제(SoT) | 판정 |
|---|---|---|---|
| `StreamDataPoint.period` 등 | **yearly** | **`YYYY-MM`** (12월 고정, 예 `2022-12`) | ❌ 계약(`YYYY`)과 불일치 |
| 동일 | monthly/quarterly | `YYYY-MM` | — |
| `TimeseriesEnvelope.requested/actual_from/to` | 전 granularity | 항상 `YYYY-MM` | ❌ yearly도 `YYYY` 아님 |
| `AnomalyDensityPoint.period` (minimap density) | yearly | **`YYYY`** (예 `2022`) | ✅ 유일하게 연도 |
| `FreshnessResponse.next_run_date` | — | `YYYY-MM-DD` (validator 강제) | ✅ |
| `FreshnessResponse.last_updated` | — | ISO 8601 (validator 없음, DB 원시값) | ⚠️ 관대한 파싱 권장 |

- 코드 경로: `aggregation.py:36 date(y,12,1)` → `timeseries.py:15 strftime("%Y-%m")`
- **FE 합의**:
  - yearly 시계열 period = **`YYYY-MM`(12월)** 로 파싱. `YYYY` 가정 시 전체 렌더 오류.
  - minimap density period만 **`YYYY`** — 별도 타입, 시계열 period와 혼용 금지.
  - `last_updated`는 ISO 8601 관대 파싱.

---

## 5. anomaly 패널 응답

| 계약 | 백엔드 실제(SoT) | 판정 |
|---|---|---|
| **H5** IRF에 anomaly_id 없음 | `IRFResponse = {commodity_id, segment_id, irfs[]}` — anomaly_id 없음 (`panel.py:72-76`) | ✅ 미반환 확정 |
| **L1** rocket_feather_direction | `upward_stronger` \| `downward_stronger` \| `null` (3값, **symmetric 없음**) | ✅ |
| **L2** ml-map 빈 응답/projection | rows 없으면 200 `points=[]`(404 아님). projection `pca`\|`feature_direct`(기본 pca). x/y_label 기본 `PC1`/`PC2` | ✅ |
| **L3** scatter until | DB 필터 아님 — 검증 후 **패스스루 메타데이터**. 미전달 시 `null` | ✅ |
| **L6** IrfCurve.subperiod_index | `scope='full'`→`null`, `scope='subperiod'`→정수 | ✅ |
| stat_metrics 필드수 | **31개** (계약 ~30 근사 일치) | ✅ |
| ml_summary 필드수 | **11개**. `if/lof/svm_anomaly`는 **항상 bool(null 금지)** | ✅ |

- **FE 합의**:
  - `rocket_feather_direction` null = '비유의적(대칭)' 처리. (스키마는 `str|None`, Literal 미강제 — FE 방어적 처리 권장)
  - `*_anomaly` 3종은 Optional 처리 금지(항상 bool).
  - `StatMetrics.subperiod_index`는 현재 서비스에서 **항상 null 하드코딩**(구현 미완, `anomaly_panel.py:168`) — FE는 null 전제.

### L4. UNTIL_EXCEEDS_TO — 검증 기준 정정
- 백엔드 검증: `until < analysis_start OR until > analysis_end` (요청 `to`가 아닌 **분석 가용 범위** 기준). HTTP 400 / `UNTIL_EXCEEDS_TO`.
- 근거: `scatter.py:68-83`
- **FE 합의**: until 검증 기준을 `to`가 아닌 **analysis_start~analysis_end**로 맞출 것. 또한 `UNTIL_EXCEEDS_TO`를 PERMANENT_FAILURE류로 등록해 무한 retry 방지.

---

## 6. 엔드포인트 표면 (18종) · 기본값

| 경로 | 필수 | 선택(기본값) |
|---|---|---|
| `GET /commodities` | — | — |
| `GET /commodities/{id}` | path | — |
| `GET /segments` · `/events` · `/freshness` | — | — |
| `GET /anomalies/summary` | — | `grade='high,medium'`, `month=YYYY-MM?` ※수용함(M6) |
| `GET /commodities/{id}/stream` | — | `granularity='monthly'`, `segments?`, `grade='high,medium'`, `patterns='pattern1,pattern2,pattern3'`, **`from?`·`to?` 수신함(M3)** |
| `GET /commodities/{id}/stream/minimap` | — | `segments?` (from/to/grade/patterns 없음) |
| `GET /commodities/{id}/scatter` | `segment` | `from?`·`to?`·`until?`·`grade='high,medium'` |
| `GET /commodities/{id}/raw-prices` | — | `layout=1`(1~6), `granularity='monthly'`, `from?`·`to?` |
| `GET /commodities/{id}/raw-prices/minimap` | — | `layout=1`(1~6) |
| `GET /anomalies/{id}/detail` | path | — |
| `GET /anomalies/{id}/stat-series` | — | `metric='transmission_rate'`(6값¹), `granularity='monthly'`, `from?`·`to?` |
| `GET /anomalies/{id}/stat-snapshot` | — | `metric='iqr'`(iqr\|asymmetry) |
| `GET /anomalies/{id}/irf` | — | `include_subperiods=true` |
| `GET /anomalies/{id}/ml-map` | — | `model='isolation_forest'`(if\|lof\|ocsvm), `projection_method='pca'`(pca\|feature_direct) |
| `GET /meta/config`·`/meta/pipeline`·`/meta/analysis-params` | — | — |
| `POST /admin/batch/trigger` | — | **202 반환**(200 아님) |

¹ stat-series metric 허용 = `transmission_rate·zscore·ect·breakpoints·iqr·asymmetry`. **iqr·asymmetry 전달 시 400 `SNAPSHOT_METRIC_ON_SERIES`**.

- **M1 prefix** `/api/v1` 고정 ✅ — baseURL에 포함.
- **M3 /stream from/to**: 백엔드는 **실제로 수신·처리**(기본 None=전체기간). **계약의 "FORBIDDEN"은 백엔드 SoT와 불일치 → 계약 문구 수정 필요.** FE는 생략 가능, 지정 시 해당 범위 필터.
- **M6 /anomalies/summary**: grade·month 수용(현재 서비스는 스텁 — `total_count=0` 반환). 실데이터는 Phase7-stat 연결 후.

---

## 7. 백엔드 측 선제 통보 (백엔드가 고칠 사안 — FE 영향)

1. **/stream 캐시키 버그** — `commodities.py:83-87` 캐시키에 `grade`·`patterns` 누락. 필터 달라도 잘못된 캐시 HIT 가능. → 백엔드 수정 예정. 그 전까지 FE는 grade/patterns 변경 시 캐시 오염 가능성 인지.
2. **anomaly_summary 스텁** — `/anomalies/summary` 현재 `total_count=0` 더미. 실데이터 Phase7-stat 연결 후.
3. **이벤트 commodity_id 표기 혼재** — 일부 데이터에 `palmoil`/`palm_oil` 혼용 가능(마이그레이션 시드 불일치). 이벤트↔품목 매칭 정합화 후 회신.
4. **anomaly_summary grade 오류 public_code** — `API-VAL-001` 노출(의미코드 정정 예정).

---

## 8. 합의 분류 요약

- **✅ 즉시 합의(백엔드=정본 그대로)**: 1-2 매핑 대부분, H1/H2/H3/H6, C1, M4, M7, H5, L1, L2, L3, L6, stat_metrics/ml_summary, M1/M6, 엔드포인트 기본값.
- **🔧 FE 수정 필요(백엔드 SoT 따름)**: M5(yearly=`YYYY-MM`), public_code 위치(`error.code`), WHOLESALE_NOT_AVAILABLE·SNAPSHOT_METRIC_ON_SERIES(400), ML_MAP_NOT_READY(200 빈응답), UNTIL_EXCEEDS_TO(analysis_end 기준), ModelType에 TECM·asymmetric_VAR 추가.
- **📝 계약 문구 수정**: M3(/stream from/to는 허용).
- **🐞 백엔드 수정 후 재공지**: /stream 캐시키, anomaly_summary 스텁·grade public_code, palmoil 표기.

> 끝. 본 회신은 커밋 `ed79246` 코드 기준 verbatim 검증 결과이며, 백엔드 변경 시 버전 올려 갱신.
