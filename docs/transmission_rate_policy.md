# `transmission_rate` 산출 단위 및 Outlier 정책

**대상 응답 필드**: `/anomalies/{id}/detail.stat_metrics.transmission_rate`,
`/anomalies/{id}/stat-series` (metric=transmission_rate),
`/commodities/{id}/stream` (전 구간),
`/anomalies/summary.anomalies[].transmission_rate`

**근거 문서**: `docs/phase7_threshold.md` (Phase 7 임계값 기록 v1, 2026-05-06)
**산출 코드**: `pipeline/preprocessing/Phase7/phase7_common.py::compute_transmission_rate`

---

## 1. 산출식

```
transmission_rate = downstream_pct / upstream_pct
```

- `downstream_pct`: 하류 가격의 전월 대비 변화율 (%, ex. 0.025 = 2.5%)
- `upstream_pct`: 상류 가격의 전월 대비 변화율 (%)

**구간별 상·하류 정의**: `segments` 테이블 `upstream_col`/`downstream_col` 참조 (예: A 구간 = `intl_price_krw` → `import_price_usd`)

---

## 2. 단위 (D1: 분모 처리 — A안 NaN 채택)

**dimensionless ratio (무차원 비율)**

- **0~1 비율 아님**. 음수·1.0 초과 모두 정상값.
- 예: `upstream_pct = +2%`, `downstream_pct = +1%` → `transmission_rate = 0.5` (절반 전이)
- 예: `upstream_pct = +2%`, `downstream_pct = -1%` → `transmission_rate = -0.5` (역방향 전이 = 비대칭/역전)
- 예: `upstream_pct = +1%`, `downstream_pct = +3%` → `transmission_rate = 3.0` (과잉 전이)

**분모 필터** (`TRANSMISSION_RATE_MIN_UPSTREAM = 0.5%`):
- `abs(upstream_pct) < 0.5%` 인 월은 **NaN** 처리 (DB·응답 모두 `null`).
- 사유: 분모가 0에 가까울 때 비율 폭주 방지.

---

## 3. Outlier 정책

전이율 outlier 판정은 **롤링 Z-score + IQR** 이중 기준 (`stat_timeseries`):

| 지표 | 임계값 | DB 컬럼 | API 노출 |
|---|---|---|---|
| `zscore` (롤링 48개월) | `ZSCORE_WARNING = 2.0` | `stat_timeseries.zscore` | `stat_metrics.zscore_warning` (bool) |
| `zscore` (롤링 48개월) | `ZSCORE_ALERT = 2.5` | 동상 | `stat_metrics.zscore_alert` (bool) |
| `IQR 이탈` | `IQR_MULTIPLIER = 1.5` | `stat_timeseries.iqr_lower/iqr_upper` | `stat_metrics.iqr_outlier` (bool) |

- 모든 임계값은 `pipeline/config/settings.py` (또는 `app/core/config.py::settings`)에서 통제 — **응답에 하드코딩 금지**.
- 응답 `stat_metrics.zscore_threshold_warning`/`zscore_threshold_alert` 필드에 현재 임계값을 함께 노출 (UI 비교 표시용).

---

## 4. Phase 6 구조변화 처리 (D3)

롤링 윈도우는 구조 변화 시점에서 **리셋하지 않음** (A안). 즉 단일 윈도우로 전 기간 산출.
하위 기간(subperiod)별 baseline은 `baselines.subperiod_id IS NOT NULL` 행으로 별도 저장 (D-15).
API에는 **전체 기간 baseline만 노출** (`subperiod_id IS NULL`).

---

## 5. 프론트엔드 처리 권고

1. **숫자 포맷**: `transmission_rate * 100` 으로 변환하지 말 것 — 이미 비율이므로 그대로 표시 (`0.5` → "0.50" 또는 "50%" 둘 중 일관).
2. **null 처리**: `null` 값은 분모 필터로 인한 정상 케이스. "데이터 없음"이 아닌 "산출 불가" 라벨 권장.
3. **outlier 표시**: `iqr_outlier=true` 시 점을 강조 (zscore_alert 별도 색상).
4. **음수/>1.0 표시**: 별도 색상·범례로 "역전"·"과잉" 구분 권장.

---

## 6. 추후 변경 예정

- D1 (분모 처리)·D3 (윈도우 리셋) 결정이 변경되면 본 문서·`phase7_threshold.md` 동시 갱신 필요.
- `IQR_MULTIPLIER` 변경 시 `stat_timeseries` 전량 재계산 필요 (배치 재실행).
