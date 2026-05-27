# 백엔드 패널 엔드포인트 구현 완료 — 프론트엔드 공유

**작성일**: 2026-05-20
**대상 브랜치**: `backend/test_run`
**서버**: `http://localhost:8001` (uvicorn, 개발 기동 중)
**대상 프론트엔드 체크리스트**: §5 백엔드 동시 요청 (7개 엔드포인트 + 4건 정합 요청)

---

## 0. TL;DR

- ✅ **5개 패널 엔드포인트 stub 제거 + 실데이터 응답** (`/detail`, `/stat-series`, `/stat-snapshot`, `/irf`, `/ml-map`)
- ✅ **정합 요청 #1** (`freshness.data_up_to` = `2026-02`) 처리 완료
- ✅ **정합 요청 #3** (`transmission_rate` 단위·outlier 정책) 문서화 완료 → `docs/transmission_rate_policy.md`
- ✅ **DB 9개 테이블 신규 적재** (Phase 2~7-ML 전 구간)
- ⚠️ **`/ml-map`** 은 OI-15 보류 데이터 미산출 — 빈 배열 응답 (graceful)
- ⚠️ **`/anomalies/summary`** 는 여전히 더미 — 별도 후속 작업
- ⚠️ **정합 요청 #4** (`stream.anomaly_nodes`에 high 등급 1건+) — 백엔드 코드 이슈 아님 (탐지 임계값 조정 필요)

---

## 1. 작동하는 엔드포인트 7개

전부 prefix `/api/v1` 적용. 예시 anomaly_id는 실제 DB 데이터(1712개 anomaly) 기준.

### 1-1. `GET /api/v1/freshness`

```bash
curl http://localhost:8001/api/v1/freshness
```

```json
{
  "data_up_to": "2026-02",
  "next_run_date": "2026-03-01",
  "last_updated": "2026-05-20T14:35:20Z"
}
```

→ **정합 요청 #1 처리 완료**.

---

### 1-2. `GET /api/v1/anomalies/{anomaly_id}/detail`

패널 헤더 + 4섹션 모든 메타.

```bash
curl http://localhost:8001/api/v1/anomalies/5137/detail
```

응답 예시 (요약):
```json
{
  "anomaly_id": 5137,
  "commodity_id": "banana",
  "commodity_name_kr": "바나나",
  "segment_id": "A",
  "segment_label_kr": "구간 A (국제가→수입단가)",
  "period": "2000-05",
  "primary_pattern": "pattern1",
  "pattern_types": ["pattern1"],
  "confidence_grade": "medium",
  "is_new": false,
  "stat_metrics": {
    "transmission_rate": -1.00072,
    "zscore_threshold_warning": 2.0,
    "zscore_threshold_alert": 2.5,
    "direction_reversal": true,
    "pattern1_flag_type": "direction_reversal",
    "ect_or_spread": -6.905154,
    "ect_type": "log_spread",
    "alpha_plus": null, "alpha_minus": null,
    "wald_pvalue": 0.0055,
    "asymmetry_significant": true,
    "rocket_feather_direction": "upward_stronger",
    "model_type": "VAR",
    "cointegrated": false,
    "bp_dates": [],
    "normal_lag": 2
  },
  "ml_summary": {
    "ml_vote": 0, "ml_detected": false,
    "if_anomaly": false, "if_score": null, "if_percentile": null,
    "lof_anomaly": false, "svm_anomaly": false
  },
  "judgment_path": [
    {"step": 1, "label": "통계 탐지", "value": "탐지됨", "passed": true},
    {"step": 2, "label": "패턴 분류", "value": "pattern1", "passed": true},
    {"step": 3, "label": "ML 합의 (3종)", "value": "0/3", "passed": false},
    {"step": 4, "label": "통계·ML 일치", "value": "불일치", "passed": false},
    {"step": 5, "label": "신뢰도 등급", "value": "medium", "passed": true}
  ]
}
```

**응답 스키마**: `app/schemas/anomaly.py::AnomalyDetailResponse`

**조인 데이터 소스**:
- `anomaly_results` (메인)
- `stat_timeseries` (해당 월 통계값)
- `baselines` (normal_lag, model_type, cointegrated)
- `cointegration_results` (cointegrated)
- `asymmetry_results` (alpha±, wald_pvalue, rocket_feather_direction)
- `breakpoints` (bp_dates)
- `ml_scores` (if/lof/svm score·percentile)
- `commodities`·`segments` (한글 라벨)

**예외**:
- `404` `API-ANO-001` ANOMALY_NOT_FOUND — 존재하지 않는 anomaly_id

---

### 1-3. `GET /api/v1/anomalies/{anomaly_id}/stat-series`

지표별 인라인 시계열. Redis 캐싱 적용.

**쿼리 파라미터**:
- `metric`: `transmission_rate` | `zscore` | `ect` | `breakpoints` (기본 `transmission_rate`)
- `from`: YYYY-MM (기본 anomaly period -24개월)
- `to`: YYYY-MM (기본 anomaly period +12개월)
- `granularity`: `monthly` | `quarterly` | `yearly` (기본 `monthly`)

```bash
curl "http://localhost:8001/api/v1/anomalies/5137/stat-series?metric=transmission_rate&from=2000-01&to=2003-12"
```

응답 (요약):
```json
{
  "anomaly_id": 5137,
  "commodity_id": "banana",
  "segment_id": "A",
  "metric": "transmission_rate",
  "highlight_period": "2000-05",
  "requested_from": "2000-01",
  "requested_to": "2003-12",
  "actual_from": "2000-01",
  "actual_to": "2003-12",
  "granularity": "monthly",
  "total_points": 48,
  "data": [
    {
      "period": "2000-01",
      "transmission_rate": null,
      "rolling_mean": null,
      "q1": null, "q3": null,
      "in_warmup_period": true,
      "is_breakpoint": false,
      "zscore": null,
      "ect_or_spread": -5.421,
      "ect_type": "log_spread"
    },
    ...
  ]
}
```

**예외**:
- `400` `API-MET-002` SNAPSHOT_METRIC_ON_SERIES — `metric=iqr` 또는 `metric=asymmetry`는 `/stat-snapshot` 사용
- `400` `API-MET-001` INVALID_METRIC / INVALID_GRANULARITY / INVALID_DATE_RANGE
- `404` ANOMALY_NOT_FOUND

---

### 1-4. `GET /api/v1/anomalies/{anomaly_id}/stat-snapshot`

비시계열 단일 시점 지표.

#### metric=iqr (롤링 IQR 박스플롯)

```bash
curl "http://localhost:8001/api/v1/anomalies/5137/stat-snapshot?metric=iqr"
```

```json
{
  "anomaly_id": 5137,
  "metric": "iqr",
  "period": "2000-05",
  "q1": null, "median": null, "q3": null,
  "iqr_lower": null, "iqr_upper": null,
  "current_value": -1.00072,
  "window_months": 48
}
```

> ⚠️ 위 예시는 warmup 구간(48개월 미달)이라 q1/q3 null. 다른 anomaly(2005년 이후)는 정상 값.

#### metric=asymmetry (상승/하락 전이율 분포)

```bash
curl "http://localhost:8001/api/v1/anomalies/5137/stat-snapshot?metric=asymmetry"
```

```json
{
  "anomaly_id": 5137,
  "metric": "asymmetry",
  "model_type": "asymmetric_VAR",
  "up_samples": [-0.940006, 0.341446, -2.573393, ...],
  "down_samples": [...],
  "alpha_plus": null, "alpha_minus": null,
  "wald_pvalue": 0.0055,
  "asymmetry_significant": true
}
```

> 표본 분리 기준: `stat_timeseries.upstream_pct >= 0` → up_samples, `< 0` → down_samples.

---

### 1-5. `GET /api/v1/anomalies/{anomaly_id}/irf`

```bash
curl "http://localhost:8001/api/v1/anomalies/5137/irf"
curl "http://localhost:8001/api/v1/anomalies/5137/irf?include_subperiods=false"
```

```json
{
  "commodity_id": "banana",
  "segment_id": "A",
  "irfs": [
    {
      "scope": "full",
      "label": "전체 기간",
      "estimation_start": "2000-01",
      "estimation_end": "2026-02",
      "subperiod_index": null,
      "peak_horizon": 2,
      "peak_magnitude": -0.107497,
      "data": [
        {"horizon": 0, "irf_downstream": 0.0, "irf_lower_ci": 0.0, "irf_upper_ci": 0.0},
        {"horizon": 1, "irf_downstream": 0.0394, "irf_lower_ci": -0.0174, "irf_upper_ci": 0.0961},
        {"horizon": 2, "irf_downstream": -0.1075, "irf_lower_ci": -0.1629, "irf_upper_ci": -0.0521},
        ...
      ]
    },
    {
      "scope": "subperiod",
      "label": "하위 기간 1",
      "subperiod_index": 1,
      "estimation_start": "2000-01",
      "estimation_end": "2013-04",
      "peak_horizon": ..., "peak_magnitude": ...,
      "data": [...]
    }
  ]
}
```

`include_subperiods=true`(기본) 시 `subperiods` 테이블의 모든 하위 기간 IRF curve 포함.

---

### 1-6. `GET /api/v1/anomalies/{anomaly_id}/ml-map`

```bash
curl "http://localhost:8001/api/v1/anomalies/5137/ml-map?model=isolation_forest&projection_method=pca"
```

**현재 응답** (OI-15 보류로 데이터 미산출):
```json
{
  "anomaly_id": 5137,
  "commodity_id": "banana",
  "segment_id": "A",
  "model": "isolation_forest",
  "projection_method": "pca",
  "x_label": "PC1",
  "y_label": "PC2",
  "total_points": 0,
  "points": []
}
```

→ 404 대신 빈 배열로 응답. 데이터 적재되면 `points`만 채워짐. 프론트는 `total_points === 0`으로 분기.

---

### 1-7. `GET /api/v1/commodities/{commodity_id}/raw-prices`

이미 존재 (변경 없음). 필드명 `import_price_usd` / `intl_price_usd` 그대로 유지 (프론트 P0-1 USD suffix 수용 전제).

---

## 2. DB 적재 현황 (2026-05-20 기준)

| 테이블 | 행수 | 소스 |
|---|---|---|
| `stat_timeseries` | 8,785 | phase7/stat_timeseries/*.csv |
| `anomaly_results` | 1,712 | phase7/pattern1·2·3 + phase7_ml/confidence_grades |
| `baselines` | 33 | phase4/baseline/*.json |
| `model_params` | 33 | phase4/model_params/*.json |
| `irf_data` | 825 | phase4/irf/*.csv (33 segment × 25 horizon) |
| `breakpoints` | 33 | phase6/breakpoints/*.json |
| `subperiods` | 12 | phase6/subperiod_models/*.json |
| `cointegration_results` | 33 | phase3/cointegration_results.csv |
| `stationarity_results` | 43 | phase2/stationarity_results.csv |
| `granger_results` | 6 | phase5/granger_results.csv |
| `asymmetry_results` | 20 | phase7/pattern2/*_asymmetry.csv |
| `ml_scores` | 4,813 | phase7_ml/predictions/*.csv |
| `ml_projections` | 0 | (OI-15 보류) |
| `data_freshness` | latest = **2026-02** | baseline.json::estimation_period_end |

---

## 3. 정책 확정 — `transmission_rate` 단위/Outlier

**근거 문서**: `docs/transmission_rate_policy.md` (백엔드 신규)
**원문**: `docs/phase7_threshold.md` (파이프라인 팀 v1, 2026-05-06)

### 3-1. 단위 (D1: NaN 처리 A안)

```
transmission_rate = downstream_pct / upstream_pct
```

- **dimensionless ratio (무차원 비율)** — 0~1 비율 아님.
- 음수, 1.0 초과 모두 **정상값**.
  - `0.5` = 절반 전이
  - `-0.5` = 역방향(비대칭)
  - `3.0` = 과잉 전이
- `abs(upstream_pct) < 0.5%` → **`null`** (분모 폭주 방지)

### 3-2. Outlier 임계값 (settings로 통제)

| 지표 | 임계값 | 응답 필드 |
|---|---|---|
| Z-score 주의 | `2.0` | `stat_metrics.zscore_warning` (bool) + `zscore_threshold_warning` (float) |
| Z-score 경보 | `2.5` | `stat_metrics.zscore_alert` (bool) + `zscore_threshold_alert` (float) |
| IQR 멀티플라이어 | `1.5` | `stat_metrics.iqr_outlier` (bool) |

응답에 임계값이 함께 나오므로 프론트는 **하드코딩 금지** — 응답 필드 그대로 사용.

### 3-3. 프론트 권고

1. `transmission_rate * 100` 변환 **금지** (이미 비율이므로 그대로 표시).
2. `null` = "산출 불가" 라벨 (데이터 없음 아님).
3. `iqr_outlier=true` 시 점 강조, `zscore_alert=true` 시 별도 색상.
4. 음수/>1.0 표시는 "역전"·"과잉" 범례로 구분 권장.

---

## 4. 예외 코드

5개 신규 엔드포인트가 발생시키는 예외:

| code | http | public_code | 발생 조건 |
|---|---|---|---|
| `API-ANO-001` | 404 | `ANOMALY_NOT_FOUND` | anomaly_id 미존재 |
| `API-ANO-002` | 500 | `PIPELINE_DATA_MISSING` | stat_timeseries 누락 (snapshot iqr) |
| `API-MET-001` | 400 | `INVALID_METRIC` / `INVALID_GRANULARITY` / `INVALID_DATE_RANGE` | metric/granularity/날짜 형식 오류 |
| `API-MET-002` | 400 | `SNAPSHOT_METRIC_ON_SERIES` | `/stat-series`에 `metric=iqr` 또는 `asymmetry` |
| `API-INT-001` | 500 | `INTERNAL_ERROR` | DB 조회 등 내부 오류 |

응답 envelope: `{ "error": { "code": "...", "public_code": "...", "message": "...", "context": {...} } }`

---

## 5. 알려진 잔여 이슈

### 5-1. `/anomalies/summary` 더미 (Frontend §5 충돌)
- 현재 `count=0, anomalies=[]` 고정 반환.
- `app/services/anomaly_summary.py` 별도 작업으로 실데이터 전환 예정.
- 회피책: 프론트는 패널 진입 시 `anomaly_id`를 `/stream.anomaly_nodes`에서 직접 사용.

### 5-2. `/ml-map` 빈 응답 (OI-15 보류)
- `ml_projections` 테이블 데이터 없음.
- 프론트는 `total_points === 0`이면 "ML 결과 준비 중" 안내 UI 분기.

### 5-3. `stream.anomaly_nodes`에 high 등급 희소 (정합 요청 #4)
- 백엔드 코드 변경 사항 아님.
- 원인: `confidence_grades` 산출 알고리즘 임계값 (`agreement` + `ml_consensus_count`).
- 해결: 파이프라인 팀 측 임계값 조정 + `phase7_ml_run.py` 재실행 + 재적재 필요.
- 임시 회피: 등급 필터를 `high,medium` 으로 (현재 기본값 그대로).

### 5-4. asymmetry_results 데이터 분포
- 20 segment (A, B 구간만, 10 commodity × 2 = 20).
- C, D, D_prime 구간 anomaly의 `stat_metrics.alpha_plus` 등은 **항상 null** (정상).

---

## 6. 환경

- 서버: `http://localhost:8001` (0.0.0.0 바인딩, 외부 접근 가능)
- CORS 허용: `http://localhost:5173` (`.env::CORS_ALLOWED_ORIGINS`)
- 다른 프론트 포트 사용 시 `.env` 갱신 → 서버 재기동
- Redis 캐싱: `/stat-series`만 적용 (TTL 3600초)

---

## 7. 변경된 파일 (커밋 전)

신규:
- `load_pipeline_outputs.py` — Phase 2~7-ML 통합 로더
- `alembic/versions/0008_ml_score_projection_tables.py` — `ml_scores`/`ml_projections` 테이블 생성
- `docs/transmission_rate_policy.md` — 정합 요청 #3 정책 문서
- `docs/phase7_threshold.md` — 파이프라인 팀 임계값 문서 (upstream 병합)
- `docs/pipeline_readme/` — Phase별 README 5개 (upstream 병합)
- `tests/phase7_ml/*` — ML 평가 5축 + dashboard (upstream 병합, `src/` → `pipeline/` 경로 패치)
- `notebooks/explore_collected_data.py` — EDA 노트북 (upstream 병합)

수정:
- `app/services/anomaly_panel.py` — 5개 stub 제거, 실서비스 구현
- 시드 데이터 한글 인코딩 정정 (commodities/segments/external_events UPDATE)
- `requirements.txt` 권장 추가: `starlette>=0.37.2,<0.38.0` (fastapi 0.111.0 호환)

---

## 8. 빠른 확인 명령 모음

```bash
# data_freshness
curl http://localhost:8001/api/v1/freshness

# 임의 anomaly 가져오기 (실 ID 확인)
curl "http://localhost:8001/api/v1/commodities/banana/stream?from=2010-01&to=2012-12" | jq '.anomaly_nodes[0:3]'

# 5개 패널 엔드포인트
ID=5137
curl "http://localhost:8001/api/v1/anomalies/$ID/detail"
curl "http://localhost:8001/api/v1/anomalies/$ID/stat-series?metric=transmission_rate"
curl "http://localhost:8001/api/v1/anomalies/$ID/stat-snapshot?metric=iqr"
curl "http://localhost:8001/api/v1/anomalies/$ID/stat-snapshot?metric=asymmetry"
curl "http://localhost:8001/api/v1/anomalies/$ID/irf"
curl "http://localhost:8001/api/v1/anomalies/$ID/ml-map"
```

연동 중 이슈 발견 시 백엔드 측에서 응답 envelope의 `error.code`·`error.context` 함께 전달 부탁.
