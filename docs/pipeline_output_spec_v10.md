# 계량경제학 파이프라인 출력 명세서

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: 파이프라인 출력 명세서 (계량경제학 브랜치, v10)
**작성일**: 2026-05-26
**작성 기준** (최신 버전 자동 참조 — `abcd_vN.md` 규칙): `doc1_technical_pipeline_vN.md` / `doc2_pattern_definitions_vN.md` / `config/settings.py` / Phase 0~3 구현 코드 기준
**변경 이력**:

- v1 → v2: 당시 design_review v1 검토 반영. 주요 변경: D-01(비대칭 검정 하위 기간 미적용 확정), D-07(Chow Test 고정 3시점 명시·적재 변환 규칙 추가), D-11(월 식별자 타입 변환 규칙 명시), D-13(동월·동구간 복수 패턴 집계 규칙 추가), D-14(ML 학습 단위 명시), D-03·D-05 파생 수정.
- v2 → v3: 'palm_oil' -> 'palmoil'로 변경.
- v3 → v4: Phase 3 변경.
- v4 → v5: Phase 4 변경.
- v5 → v6: Phase 5,6 변경.
- v6 → v7 (2026-05-02): 본문 정정. `reference_audit_report v1` §4 규칙에 따라 외부 참조 표기를 `abcd_vN.md`로 일괄 전환. 헤더·본문의 구버전 참조(당시 doc1 v8) 정정. 본 문서는 이제 `docs/docs_manifest.md`의 버전 해석기에 의해 자동 최신 참조되며, 파일명·본문·푸터는 `_v7`로 정합.
- v7 → v8: 명세에 맞춰서 제작해서 기존 내용에 변경은 거의 없지만(컬럼명 변경 X) 추가 컬럼이 필요해 그 부분 반영함.
  pattern1: commodity_id, segment, insufficient_data, subperiod_id 추가
  pattern2_zscore: commodity_id, segment, upstream_pct, downstream_pct 추가
  pattern2_asymmetry: mean_tr_up, mean_tr_down, n_up, n_down 추가
  pattern3: commodity_id, segment, ect_type, ect_abs, ect_sign, abs_expanding, same_sign_streak, abs_expand_streak 추가. spread_n2/n3/n6 타입을 float→bool로 정정
  출력 디렉토리: stat_timeseries/ 폴더 추가
- v8 → v9: 파라미터 확정(
  "탐색적 결정 (0.05~0.15)" → contamination=0.08, nu=0.08 확정 명시
  모델 파라미터 전체 테이블 추가 (IF/LOF/SVM/전처리/앙상블))
  컬럼 명세 보완(
  features, predictions, cross_validation, grades 전부에 commodity_id, segment 컬럼 추가
  predictions에 svm_score 설명 보강 ("음수=이상")
  grades에 ml_consensus_count, agreement 컬럼 추가)
  새로운 출력물(
  models/{YYYYMMDD_HHMM}/ — 타임스탬프 방식 모델 저장 + pkl 파일 패턴 + run_log 명세
  phase7_ml_summary.csv — 전체 요약 컬럼 명세)
  5축 평가 프레임워크 섹션(
  코드 구조 트리, 실행 방법, 출력 파일 6종 명세
  연속형 앙상블 스코어 방식 설명
  run_meta.json 구조)
  SHAP 분석 섹션(
  3종 모델별 코드 + 대시보드 코드 구조
  출력 디렉토리 패턴 ({YYYYMMDD*HHMM}\_IF, 대시보드* 등)
  SHAP CSV + summary + run_meta.json 명세
  run_meta.json 주요 필드 (status, skipped, background_data 등))
- v9 → v10: Phase 8 출력물 추가

---

## 개요

### 명세서 목적

본 명세서는 계량경제학 파이프라인(Phase 0~7)의 각 단계가 생성하는 파일과 그 내부 구조를 정의한다. Phase 0~2는 구현 완료 코드 기준이며, Phase 3~7은 `doc1_technical_pipeline_vN` 및 `settings.py` 파라미터 기준 설계 명세다.

### 표기 원칙

- `{cid}`: 품목 식별자 (`wheat`, `maize`, `soybean`, `palmoil`, `sugar`, `coffee`, `beef`, `groundnuts`, `banana`, `orange`)
- `{seg}`: 분석 구간 식별자 (`A`, `B`, `C`, `D`, `D_prime`)
- **굵게**: Phase 간 인터페이스 역할을 하는 핵심 출력 파일
- 출력 경로 루트: `data/processed/`

### 품목 분류 요약

| 유형            | 품목 (7종)                                          | 분석 구간     |
| --------------- | --------------------------------------------------- | ------------- |
| 3구간 (A-B-D′)  | wheat, maize, soybean, palmoil, sugar, coffee, beef | A · B · D′    |
| 4구간 (A-B-C-D) | groundnuts, banana, orange                          | A · B · C · D |

### 월 식별자 타입 변환 규칙 (D-11)

파이프라인·DB·API 세 계층 간 월 식별자 표현 방식이 다르다. 각 계층의 표현 방식과 변환 책임은 다음과 같다.

| 계층                | 표현 방식                                 | 예시                      |
| ------------------- | ----------------------------------------- | ------------------------- |
| 파이프라인 (Python) | `DatetimeIndex` (Month Start, MS)         | `Timestamp('2022-03-01')` |
| DB (PostgreSQL)     | `DATE` — 반드시 **월초(YYYY-MM-01)** 고정 | `2022-03-01`              |
| API (JSON 응답)     | `YYYY-MM` 문자열                          | `"2022-03"`               |

**변환 규칙**:

1. **파이프라인 → DB 적재 시**: `DatetimeIndex` → `YYYY-MM-01` 형식 `DATE`로 변환. 적재 로직은 `period.day == 1` 검증 후 저장. 월말 기준 저장을 방지한다.
2. **DB → API 응답 시**: 백엔드 Pydantic 시리얼라이저가 `DATE`를 `YYYY-MM` 문자열로 포맷팅한다 (`strftime("%Y-%m")`). Pydantic 필드 타입은 `str` + `field_validator`로 형식을 강제한다.
3. **타임존**: 파이프라인 및 DB는 시간대 없이 날짜만 처리한다. `TIMESTAMPTZ`는 배치 실행 이력(`pipeline_runs`)에만 사용한다.

---

## Phase 0 — 데이터 수집·전처리

### 출력 디렉토리

```
data/
├── raw/
│   ├── worldbank/          ← Pink Sheet 원시 CSV
│   ├── fao/                ← FAO FFPI 원시 데이터
│   ├── customs/            ← 관세청 수입 단가 원시 데이터
│   ├── ecos/               ← 한국은행 ECOS (PPI, CPI) 원시 데이터
│   ├── kamis/              ← KAMIS 도매가 원시 데이터
│   └── exchange_rate/      ← 환율 API 원시 데이터
│
└── processed/
    ├── merged/
    │   └── {cid}.csv       ← 품목별 통합 월별 데이터셋 ← Phase 1 입력
    └── product_config.json ← 품목별 분석 설정 ← Phase 1~7 전역 참조
```

### `data/processed/merged/{cid}.csv`

Phase 0의 최종 산출물. Phase 1 입력으로 사용된다.

| 컬럼               | 타입               | 설명                                               |
| ------------------ | ------------------ | -------------------------------------------------- |
| `date`             | DatetimeIndex (MS) | 월 기준일 (인덱스)                                 |
| `commodity_id`     | str                | 품목 식별자                                        |
| `intl_price_usd`   | float              | 국제가 (달러 기준, $/톤)                           |
| `intl_price_krw`   | float              | 국제가 원화 환산 (월평균 환율 적용)                |
| `exchange_rate`    | float              | 월평균 원/달러 환율                                |
| `import_price_usd` | float              | 수입단가 (관세청, $/톤)                            |
| `ppi`              | float              | 생산자물가지수 (한국은행 ECOS, 품목별 세부 항목)   |
| `cpi`              | float              | 소비자물가지수 (한국은행 ECOS, 품목별 세부 항목)   |
| `wholesale_price`  | float \| NaN       | KAMIS 도매가 (4구간 품목만 존재, 3구간 품목은 NaN) |

**비고**: 결측치는 선형 보간 처리. 결측률 10% 초과 품목은 분석 제외.

### `data/processed/product_config.json`

전 Phase에서 공통 참조하는 품목별 분석 설정 파일.

```json
{
  "wheat": {
    "name_kr": "밀",
    "name_en": "Wheat",
    "has_wholesale": false,
    "segments": ["A", "B", "D_prime"],
    "segment_pairs": {
      "A": ["intl_price_krw", "import_price_usd"],
      "B": ["import_price_usd", "ppi"],
      "D_prime": ["ppi", "cpi"]
    },
    "common_start": "YYYY-MM",
    "common_end": "YYYY-MM",
    "common_months": 0
  },
  "groundnuts": {
    "has_wholesale": true,
    "segments": ["A", "B", "C", "D"],
    "segment_pairs": {
      "A": ["intl_price_krw", "import_price_usd"],
      "B": ["import_price_usd", "ppi"],
      "C": ["ppi", "wholesale_price"],
      "D": ["wholesale_price", "cpi"]
    }
  }
}
```

**비고**: `segment_pairs` 값의 첫 번째 원소가 상류(upstream), 두 번째가 하류(downstream).

---

## Phase 1 — 계절 조정 (Seasonal Adjustment)

**실행**: `python src/preprocessing/phase1_seasonal_adjustment.py`

**입력**: `data/processed/merged/{cid}.csv`, `data/processed/product_config.json`

**방법**: STL 분해 (period=12, robust=True). 로버스트니스용 계절 더미 방식 병행 산출.

### 출력 디렉토리

```
data/processed/phase1/
├── seasonal_adjusted/
│   └── {cid}_sa.csv            ← 원본 + 계절 조정 수준값 ← Phase 2 입력
├── changes/
│   └── {cid}_changes.csv       ← 전월 대비 변화율 (%) ← Phase 4·7 주 입력
├── stl_components/
│   └── {cid}_stl.csv           ← STL 3성분 분해
├── robustness/
│   ├── {cid}_dummy_sa.csv      ← 계절 더미 방식 계절 조정
│   └── {cid}_dummy_changes.csv ← 계절 더미 방식 변화율
└── phase1_summary.csv          ← 43개 시계열 요약 통계
```

### `seasonal_adjusted/{cid}_sa.csv`

| 컬럼           | 타입               | 설명                               |
| -------------- | ------------------ | ---------------------------------- |
| `date`         | DatetimeIndex (MS) | 월 기준일 (인덱스)                 |
| `commodity_id` | str                | 품목 식별자                        |
| `{col}`        | float              | 원본 수준값 (비교 참조용)          |
| `{col}_sa`     | float              | 계절 조정 수준값 = 원본 - seasonal |

`{col}`: `intl_price_krw`, `import_price_usd`, `ppi`, `cpi` (공통 4종) + `wholesale_price` (4구간 품목 추가)

**Phase 3 (Johansen 공적분 검정) 입력으로 사용한다.**

### `changes/{cid}_changes.csv`

| 컬럼                 | 타입               | 설명                                                 |
| -------------------- | ------------------ | ---------------------------------------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일 (인덱스)                                   |
| `commodity_id`       | str                | 품목 식별자                                          |
| `{col}_pct`          | float              | 계절 조정 후 전월 대비 변화율 (%) = pct_change × 100 |
| `exchange_rate_pct`  | float              | 환율 변화율 (STL 미적용, 원본에서 직접 산출)         |
| `intl_price_usd_pct` | float              | 달러 국제가 변화율 (STL 미적용, 원본에서 직접 산출)  |

첫 행은 NaN. `exchange_rate_pct`, `intl_price_usd_pct`는 Phase 7-ML 외생 피처로 사용.

**Phase 4·7 주 입력 파일.**

### `stl_components/{cid}_stl.csv`

| 컬럼             | 타입  | 설명          |
| ---------------- | ----- | ------------- |
| `{col}_trend`    | float | STL 추세 성분 |
| `{col}_seasonal` | float | STL 계절 성분 |
| `{col}_resid`    | float | STL 잔차 성분 |

### `phase1_summary.csv`

| 컬럼                                | 설명                                           |
| ----------------------------------- | ---------------------------------------------- |
| `commodity_id`, `column`            | 품목 및 가격 컬럼                              |
| `n_obs`                             | 관측치 수                                      |
| `original_mean`, `original_std`     | 원본 시계열 평균·표준편차                      |
| `sa_mean`, `sa_std`                 | 계절 조정 시계열 평균·표준편차                 |
| `seasonal_range`                    | 계절 성분 최댓값 - 최솟값                      |
| `seasonal_pct_of_mean`              | 계절 범위 / 원본 평균 × 100 (계절성 강도 지표) |
| `pct_change_mean`, `pct_change_std` | 변화율 통계                                    |
| `pct_change_min`, `pct_change_max`  | 변화율 범위                                    |

---

## Phase 2 — 정상성 검정 (Stationarity Test)

**실행**: `python src/preprocessing/phase2_stationarity_test.py`

**입력**: `data/processed/phase1/seasonal_adjusted/{cid}_sa.csv`, `data/processed/product_config.json`

**방법**: ADF(autolag='AIC') + KPSS(regression='c', nlags='auto') 병행 검정. 보수적 판정 원칙 — 둘 중 하나라도 비정상이면 비정상으로 처리. 비정상 시 1차 차분 후 재검정.

### 출력 디렉토리

```
data/processed/phase2/
├── stationarity_results.csv    ← ADF+KPSS 전체 검정 결과 ← Phase 3 참조
└── integration_orders.json     ← 품목·컬럼별 적분 차수 ← Phase 3 주 입력
```

### `stationarity_results.csv`

| 컬럼                     | 타입          | 설명                                              |
| ------------------------ | ------------- | ------------------------------------------------- |
| `commodity_id`, `column` | str           | 품목 및 가격 컬럼                                 |
| `n_obs`                  | int           | 관측치 수                                         |
| `level_adf_stat`         | float         | 수준 ADF 검정 통계량                              |
| `level_adf_pvalue`       | float         | 수준 ADF p값                                      |
| `level_adf_lags`         | int           | ADF 선택 시차 (AIC 기준)                          |
| `level_adf_stationary`   | bool          | 수준 ADF 정상 여부 (p < 0.05)                     |
| `level_kpss_stat`        | float         | 수준 KPSS 검정 통계량                             |
| `level_kpss_pvalue`      | float         | 수준 KPSS p값 ([0.01, 0.10] 클리핑)               |
| `level_kpss_stationary`  | bool          | 수준 KPSS 정상 여부 (p ≥ 0.05)                    |
| `level_judgment`         | str           | 수준 최종 판정 (`stationary` \| `non-stationary`) |
| `level_conflict_note`    | str           | ADF-KPSS 일치/상충 여부                           |
| `diff_adf_stat`          | float \| None | 차분 ADF 통계량 (비정상 시에만)                   |
| `diff_adf_pvalue`        | float \| None | 차분 ADF p값                                      |
| `diff_kpss_stat`         | float \| None | 차분 KPSS 통계량                                  |
| `diff_kpss_pvalue`       | float \| None | 차분 KPSS p값                                     |
| `diff_judgment`          | str \| None   | 차분 최종 판정                                    |
| `integration_order`      | int           | 적분 차수 (0, 1, 또는 2)                          |

### `integration_orders.json`

Phase 3의 주 입력 파일. 품목·컬럼별 적분 차수를 저장한다.

```json
{
  "wheat": {
    "cpi": 1,
    "import_price_usd": 1,
    "intl_price_krw": 1,
    "ppi": 1
  },
  "groundnuts": {
    "cpi": 1,
    "import_price_usd": 1,
    "intl_price_krw": 1,
    "ppi": 1,
    "wholesale_price": 2
  }
}
```

**비고**: I(2) 시계열 포함 구간은 Phase 3에서 주의 플래그 부착 후 I(1)으로 간주하고 진행. 땅콩 `wholesale_price`(I(2)), 오렌지 `intl_price_krw`(I(2)) 확인됨.

---

## Phase 3 — 장기 균형 관계 검정 (Johansen 공적분 검정)

**입력**: `phase1/seasonal_adjusted/{cid}_sa.csv` (수준 데이터), `phase2/integration_orders.json`

**방법**: Johansen 공적분 검정 (det_order=0). Trace 통계량 + Max-Eigen 통계량 병행. I(1) 쌍 우선 검정, I(2) 포함 구간은 주의 플래그 부착 후 진행. 결과에 따라 VECM 또는 VAR 경로로 분기. Johansen 검정은 p값이 아닌 통계량과 임계값(5%) 비교 방식이며, Trace와 Max-Eigen 모두 기각 시 공적분 확정, Trace만 기각 시 Trace 우선 적용.

### 출력 디렉토리

```
data/processed/phase3/
├── cointegration_results.csv       ← 구간별 공적분 검정 결과 ← Phase 4 입력
└── model_routing.json              ← 품목·구간별 모형 경로 (VAR/VECM) ← Phase 4 주 입력
```

### `cointegration_results.csv`

| 컬럼               | 타입       | 설명                                                           |
| ------------------ | ---------- | -------------------------------------------------------------- |
| `commodity_id`     | str        | 품목 식별자                                                    |
| `segment`          | str        | 분석 구간 (A, B, C, D, D_prime)                                |
| `upstream`         | str        | 상류 가격 컬럼명                                               |
| `downstream`       | str        | 하류 가격 컬럼명                                               |
| `n_obs`            | int        | 관측치 수                                                      |
| `var_lag_aic`      | int        | VAR 최적 시차 (AIC 기준)                                       |
| `var_lag_bic`      | int        | VAR 최적 시차 (BIC 기준)                                       |
| `johansen_lag`     | int        | Johansen 검정 시차 (var_lag_aic - 1, 최소 1)                   |
| `trace_stat_r0`    | float      | Johansen Trace 통계량 (r=0 검정)                               |
| `trace_crit_r0`    | float      | Trace 임계값 (5% 유의수준)                                     |
| `trace_reject_r0`  | bool       | Trace 기각 여부 (stat > crit)                                  |
| `eigen_stat_r0`    | float      | Max-Eigenvalue 통계량 (r=0 검정)                               |
| `eigen_crit_r0`    | float      | Max-Eigen 임계값 (5% 유의수준)                                 |
| `eigen_reject_r0`  | bool       | Max-Eigen 기각 여부 (stat > crit)                              |
| `cointegrated`     | bool       | 공적분 존재 여부 (최종 판정)                                   |
| `judgment_note`    | str        | 판정 근거 설명 (예: "Trace·Max-Eigen 모두 기각 → 공적분 확정") |
| `model_selected`   | str        | 선택 모형 (`VECM` \| `VAR`)                                    |
| `integration_flag` | str \| NaN | I(2) 포함 시 주의 메시지, 정상 쌍은 NaN                        |

**비고**: Johansen 검정은 ADF와 달리 p값을 반환하지 않는다. 통계량이 임계값을 초과하면 귀무가설(공적분 없음)을 기각한다.

### `model_routing.json`

Phase 4의 주 입력 파일. 구간별 추정 모형과 시차를 지정한다.

```json
{
  "wheat": {
    "A": {
      "model": "VECM",
      "cointegrated": true,
      "upstream": "intl_price_krw",
      "downstream": "import_price_usd",
      "var_lag_aic": 4,
      "johansen_lag": 3
    },
    "B": {
      "model": "VECM",
      "cointegrated": true,
      "upstream": "import_price_usd",
      "downstream": "ppi",
      "var_lag_aic": 4,
      "johansen_lag": 3
    },
    "D_prime": {
      "model": "VECM",
      "cointegrated": true,
      "upstream": "ppi",
      "downstream": "cpi",
      "var_lag_aic": 4,
      "johansen_lag": 3
    }
  },
  "groundnuts": {
    "A": {
      "model": "VECM",
      "cointegrated": true,
      "upstream": "intl_price_krw",
      "downstream": "import_price_usd",
      "var_lag_aic": 2,
      "johansen_lag": 1
    },
    "B": {
      "model": "VAR",
      "cointegrated": false,
      "upstream": "import_price_usd",
      "downstream": "ppi",
      "var_lag_aic": 3,
      "johansen_lag": 2
    },
    "C": {
      "model": "VAR",
      "cointegrated": false,
      "upstream": "ppi",
      "downstream": "wholesale_price",
      "var_lag_aic": 2,
      "johansen_lag": 1
    },
    "D": {
      "model": "VAR",
      "cointegrated": false,
      "upstream": "wholesale_price",
      "downstream": "cpi",
      "var_lag_aic": 2,
      "johansen_lag": 1
    }
  }
}
```

**비고**: Phase 4에서 VECM 구간은 `johansen_lag`를, VAR 구간은 `var_lag_aic`를 시차로 사용한다. `granger_direction`은 Phase 5 완료 후 4구간 품목 구간 C에만 추가 갱신

---

## Phase 4 — 모형 추정 및 기준선 산출 (VAR/VECM + IRF)

**입력**: `phase1/changes/{cid}_changes.csv` (변화율, VAR용), `phase1/seasonal_adjusted/{cid}_sa.csv` (수준, VECM용), `phase3/model_routing.json`

**방법**: 구간별 `model_routing.json` 기준으로 VAR 또는 VECM 추정. 시차는 Phase 3에서 결정된 값을 사용 (VECM: `johansen_lag`, VAR: `var_lag_aic`). Phase 4에서 시차를 재선택하지 않는다. IRF는 VAR/VECM 추정 후 0~24개월(IRF_HORIZON=24) 범위로 산출.

### 출력 디렉토리

```
data/processed/phase4/
├── model_params/
│   └── {cid}_{seg}_model.json      ← 추정 모형 파라미터
├── irf/
│   └── {cid}_{seg}_irf.csv         ← IRF 시계열 ← Phase 7 패턴 1 기준선 입력
├── baseline/
│   └── {cid}_{seg}_baseline.json   ← 기준선 테이블 ← Phase 7 주 참조
├── ect/
│   └── {cid}_{seg}_ect.csv         ← ECT (VECM) 또는 로그 스프레드 (VAR) ← Phase 7-ML 피처
└── phase4_summary.csv              ← 전 품목·구간 추정 요약
```

### `model_params/{cid}_{seg}_model.json`

VECM과 VAR에서 포함되는 필드가 다르다.

**VECM 예시:**

```json
{
  "commodity_id": "wheat",
  "segment": "A",
  "upstream_col": "intl_price_krw",
  "downstream_col": "import_price_usd",
  "lag_selection_criterion": "AIC",
  "model_type": "VECM",
  "lag_selected": 3,
  "n_obs": 300,
  "cointegrated": true,
  "det_order": 0,
  "coint_rank": 1,
  "alpha": [[-0.014], [0.000083]],
  "beta": [[1.0], [-1359.84]]
}
```

**VAR 예시:**

```json
{
  "commodity_id": "coffee",
  "segment": "A",
  "upstream_col": "intl_price_krw",
  "downstream_col": "import_price_usd",
  "lag_selection_criterion": "AIC",
  "model_type": "VAR",
  "lag_selected": 2,
  "n_obs": 58,
  "cointegrated": false,
  "det_order": null,
  "coint_rank": null,
  "aic": 8.5008,
  "bic": 8.8561
}
```

**비고**: VECM에만 `alpha`(조정 계수), `beta`(공적분 벡터) 포함. VAR에만 `aic`, `bic` 포함.

### `irf/{cid}_{seg}_irf.csv`

충격반응함수 시계열. Phase 7 패턴 1의 정상 전달 시차 산출에 사용.

| 컬럼                 | 타입  | 설명                                                         |
| -------------------- | ----- | ------------------------------------------------------------ |
| `horizon`            | int   | 충격 후 경과 기간 (개월, 0~24)                               |
| `irf_downstream`     | float | 하류 가격의 상류 충격에 대한 반응                            |
| `irf_lower_ci`       | float | IRF 95% 신뢰구간 하한 (stderr 기반)                          |
| `irf_upper_ci`       | float | IRF 95% 신뢰구간 상한 (stderr 기반)                          |
| `irf_peak_horizon`   | int   | IRF 피크 도달 시점 (정상 전달 시차 기준값, 모든 행에 동일값) |
| `irf_peak_magnitude` | float | IRF 피크 크기 (전이탄력성 기준값, 모든 행에 동일값)          |

**비고**: 피크는 IRF 절대값 최대 시점으로 선택. 음수 반응(역방향 전달)도 포착하기 위해 절대값 기준 사용.

### `baseline/{cid}_{seg}_baseline.json`

Phase 7 이상 탐지의 기준선 파라미터. **전체 기간 기준선만 산출** (하위 기간별 기준선은 `subperiod_models/` 참조).

```json
{
  "commodity_id": "wheat",
  "segment": "A",
  "normal_transmission_lag": 18,
  "transmission_elasticity": 0.000678,
  "warmup_end": "2004-01",
  "model_type": "VECM",
  "estimation_period_start": "2000-01",
  "estimation_period_end": "2024-12",
  "n_obs": 300
}
```

| 필드                      | 설명                                                                          |
| ------------------------- | ----------------------------------------------------------------------------- |
| `normal_transmission_lag` | IRF 피크 도달 시점 (개월) — 패턴 1 시차 이탈 판정 기준                        |
| `transmission_elasticity` | IRF 피크 크기 — 패턴 2 전이율 정상 수준 참조값                                |
| `warmup_end`              | 롤링 윈도우 48개월 축적 완료 시점. `estimation_period_start` + 48개월로 산출. |

### `ect/{cid}_{seg}_ect.csv`

모든 구간에서 생성 (VECM·VAR 모두). VECM 구간은 오차수정항(ECT), VAR 구간은 로그 수준 스프레드로 대체.

| 컬럼       | 타입               | 설명                                        |
| ---------- | ------------------ | ------------------------------------------- |
| `date`     | DatetimeIndex (MS) | 월 기준일 (인덱스)                          |
| `ect`      | float              | ECT 값 (VECM) 또는 로그 수준 스프레드 (VAR) |
| `ect_type` | str                | `"ECT"` \| `"log_spread"`                   |

**비고**: ECT = β' × Y_t (공적분 벡터 × 수준 데이터). 로그 스프레드 = log(하류\_sa) - log(상류\_sa). Phase 7 패턴 3 및 Phase 7-ML 입력 피처 (6종 중 하나)로 직접 사용.

### `phase4_summary.csv`

| 컬럼               | 타입  | 설명                       |
| ------------------ | ----- | -------------------------- |
| `commodity_id`     | str   | 품목 식별자                |
| `segment`          | str   | 분석 구간                  |
| `model_type`       | str   | VECM / VAR                 |
| `lag`              | int   | 사용된 시차                |
| `n_obs`            | int   | 관측치 수                  |
| `peak_horizon`     | int   | IRF 피크 시점 (개월)       |
| `peak_magnitude`   | float | IRF 피크 크기 (전이탄력성) |
| `ect_type`         | str   | ECT / log_spread           |
| `estimation_start` | str   | 추정 시작 월 (YYYY-MM)     |
| `estimation_end`   | str   | 추정 종료 월 (YYYY-MM)     |

---

## Phase 5 — 인과 방향 확정 (Granger 인과 검정)

**적용 대상**: 4구간 품목 (groundnuts, banana, orange) 구간 C (PPI↔도매가)만 적용. 3구간 품목 및 기타 구간은 Phase 5 생략.

**입력**: `phase1/changes/{cid}_changes.csv` (변화율), `phase3/model_routing.json`

**방법**: 양방향 Granger 인과 검정 (PPI→도매가, 도매가→PPI). 유의 방향으로 구간 C 분석 방향 확정.

### 출력 디렉토리

```
data/processed/phase5/
└── granger_results.csv         ← Granger 검정 결과 및 확정 방향
└── granger_direction.json      ← 품목별 최종 확정 인과 방향 (후속 분석 참조용)
```

### `granger_results.csv`

| 컬럼                  | 타입  | 설명                                                                                        |
| --------------------- | ----- | ------------------------------------------------------------------------------------------- |
| `commodity_id`        | str   | 품목 식별자 (4구간 3종만)                                                                   |
| `segment`             | str   | 분석 구간 (C 고정)                                                                          |
| `direction`           | str   | 검정 방향 (`ppi_to_wholesale` \| `wholesale_to_ppi`)                                        |
| `max_lag`             | int   | 검정에 사용된 최대 시차                                                                     |
| `best_lag`            | int   | 1부터 max_lag 사이에서 p-value(ssr_ftest)가 최소가 되는 최적 시차                           |
| `f_stat`              | float | F 통계량                                                                                    |
| `pvalue`              | float | p값                                                                                         |
| `significant`         | bool  | 유의 여부 (p < 0.05)                                                                        |
| `confirmed_direction` | str   | 최종 확정 인과 방향 (`ppi_to_wholesale` \| `wholesale_to_ppi` \| `bidirectional` \| `none`) |

### `confirmed_direction` 판정 로직 및 Phase 7 적용 범위

| 결과               | 조건                                                | Phase 7 적용    |
| ------------------ | --------------------------------------------------- | --------------- |
| `ppi_to_wholesale` | PPI→도매가만 유의                                   | 패턴 1·2·3 모두 |
| `wholesale_to_ppi` | 도매가→PPI만 유의                                   | 패턴 1·2·3 모두 |
| `bidirectional`    | 양방향 유의 (PL-P5-003) — PPI→도매가 기본 방향 유지 | 패턴 1·2·3 모두 |
| `none`             | 양방향 비유의 (PL-P5-002)                           | 패턴 1만        |

### 'granger_direction.json'

품목별 최종 확정 인과 방향 (후속 분석 참조용)

```json
{
  "groundnuts": {
    "segment": "C",
    "confirmed_direction": "bidirectional"
  },
  "banana": {
    "segment": "C",
    "confirmed_direction": "none"
  },
  "orange": {
    "segment": "C",
    "confirmed_direction": "none"
  }
}
```

---

## Phase 6 — 구조 변화 탐지 및 기간 분할

**입력**: `phase1/changes/{cid}_changes.csv`, `phase1/seasonal_adjusted/{cid}_sa.csv`, `phase3/model_routing.json`, `phase4/baseline/{cid}_{seg}_baseline.json`, `product_config.json`

**방법**: 전이율(하류 변화율 ÷ 상류 변화율) 시계열에 Bai-Perron 구조 변화 검정 (Dynp + BIC, 데이터 주도 변화 시점 탐지) + Chow Test (2008·2020·2022 사전 지정 3개 시점 교차 확인). 전이율 산출 시 상류 변화율 절대값 < 3% 구간은 NaN 처리 후 forward-fill (Phase 7 STABILITY_THRESHOLD와 동일). 하위 기간 최소 관측치 60개 (`MIN_SUBPERIOD_OBS = 60`). 미달 시 인접 기간과 병합.

**경계 사례 플래그**: Phase 3에서 공적분 Trace가 임계값 ±10% 이내이거나, 데이터 확장으로 모형이 전환됐거나, I(2) 플래그가 붙은 구간에 `borderline_cointegration: true`를 부착. 하위 기간 재추정 결과의 해석 시 주의 표시.

**Chow Test 고정 시점 (D-07)**: Chow Test는 `2008-01`, `2020-01`, `2022-01` **정확히 3개 시점**을 항상 검정한다. 추가 또는 축소 없이 고정. DB `breakpoints` 테이블의 `chow_2008_*`, `chow_2020_*`, `chow_2022_*` 컬럼 구조에 1:1 대응.

### 출력 디렉토리

```
data/processed/phase6/
├── breakpoints/
│   └── {cid}_{seg}_breakpoints.json    ← 변화 시점 및 하위 기간 분할 정보
├── chow_results/
│   └── {cid}_{seg}_chow.csv            ← Chow Test 결과
├── subperiod_models/
│   └── {cid}_{seg}_subperiod_{n}_model.json  ← 하위 기간별 재추정 모형 파라미터
└── phase6_summary.csv                  ← 전 품목·구간 요약
```

### `breakpoints/{cid}_{seg}_breakpoints.json`

```json
{
  "commodity_id": "wheat",
  "segment": "D_prime",
  "borderline_cointegration": false,
  "bai_perron_breakpoints": ["2013-05", "2020-11"],
  "bai_perron_best_k": 2,
  "bic_scores": {
    "0": -62.9,
    "1": -67.57,
    "2": -362.49,
    "3": -350.52,
    "4": -245.59
  },
  "chow_test_points": {
    "2008-01": {
      "break_point": "2008-01",
      "f_stat": 7.3014,
      "pvalue": 0.0008,
      "significant": true
    },
    "2020-01": {
      "break_point": "2020-01",
      "f_stat": 103.4496,
      "pvalue": 0.0,
      "significant": true
    },
    "2022-01": {
      "break_point": "2022-01",
      "f_stat": 96.2219,
      "pvalue": 0.0,
      "significant": true
    }
  },
  "subperiods": [
    { "id": 1, "start": "2000-01", "end": "2013-04", "n_obs": 160 },
    { "id": 2, "start": "2013-05", "end": "2020-10", "n_obs": 90 },
    { "id": 3, "start": "2020-11", "end": "2026-02", "n_obs": 64 }
  ]
}
```

| 필드                       | 설명                                                                                                                                                                              |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `borderline_cointegration` | 경계 사례 플래그. Phase 3 공적분 검정이 아슬하거나 I(2) 플래그가 부착된 구간은 `true`                                                                                             |
| `bai_perron_breakpoints`   | Bai-Perron이 탐지한 구조 변화 시점 목록 (`"YYYY-MM"` 형식). 탐지 없으면 빈 배열                                                                                                   |
| `bai_perron_best_k`        | BIC 기준 최적 변화점 수 (0이면 변화점 없음)                                                                                                                                       |
| `bic_scores`               | 변화점 수(k=0,1,2,...) 별 BIC 점수. 최소 BIC의 k가 `bai_perron_best_k`                                                                                                            |
| `chow_test_points`         | 고정 3개 시점별 Chow Test 결과. 각 항목에 `break_point`, `f_stat`, `pvalue`, `significant` 포함. 분석 범위 밖이면 `f_stat`·`pvalue`·`significant`가 `null`이고 `note`에 사유 기재 |
| `subperiods`               | 확정된 하위 기간 목록. `n_obs` < 60인 기간은 `merged_with`로 병합 대상 `id` 기재                                                                                                  |

### `chow_results/{cid}_{seg}_chow.csv`

| 컬럼           | 타입  | 설명                                                                  |
| -------------- | ----- | --------------------------------------------------------------------- |
| `commodity_id` | str   | 품목 식별자                                                           |
| `segment`      | str   | 분석 구간                                                             |
| `break_point`  | str   | Chow 검정 시점 (`2008-01` \| `2020-01` \| `2022-01`)                  |
| `f_stat`       | float | F 통계량. 범위 밖이면 빈값                                            |
| `pvalue`       | float | p값. 범위 밖이면 빈값                                                 |
| `significant`  | bool  | 유의 여부 (p < 0.05). 범위 밖이면 빈값                                |
| `note`         | str   | 비고. `분석 범위 밖 (PL-P6-002)` 또는 `구간 관측치 부족 (전=N, 후=M)` |

### `subperiod_models/{cid}_{seg}_subperiod_{n}_model.json`

하위 기간별 VAR/VECM 재추정 결과. 2개 이상 독립 하위 기간이 있을 때만 생성.

```json
{
  "model_type": "VECM",
  "lag_selected": 3,
  "n_obs": 160,
  "cointegrated": true,
  "det_order": 0,
  "coint_rank": 1,
  "alpha": [[-0.2257], [0.2479]],
  "beta": [[1.0], [-0.8901]],
  "subperiod_index": 1,
  "subperiod_start": "2000-01",
  "subperiod_end": "2013-04",
  "commodity_id": "wheat",
  "segment": "D_prime",
  "upstream_col": "ppi",
  "downstream_col": "cpi",
  "effective_lag": 3,
  "original_lag": 3,
  "irf_peak_horizon": 24,
  "irf_peak_magnitude": 1.129387
}
```

| 필드                                                                                | 설명                                                                                         |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `model_type`                                                                        | 모형 유형 (`VECM` \| `VAR`). 전체 기간 `model_routing.json`의 모형을 하위 기간에도 동일 적용 |
| `lag_selected`, `n_obs`, `cointegrated`, `det_order`, `coint_rank`, `alpha`, `beta` | Phase 4 추정 함수의 표준 출력 필드                                                           |
| `subperiod_index`                                                                   | 하위 기간 번호 (1부터)                                                                       |
| `subperiod_start`, `subperiod_end`                                                  | 하위 기간 범위 (`YYYY-MM`)                                                                   |
| `commodity_id`, `segment`                                                           | 품목·구간 식별자                                                                             |
| `upstream_col`, `downstream_col`                                                    | 상류·하류 변수명                                                                             |
| `effective_lag`                                                                     | 실제 적용 시차. 하위 기간이 짧으면 `original_lag`보다 축소될 수 있음                         |
| `original_lag`                                                                      | 전체 기간 기준 시차 (`model_routing.json`의 `johansen_lag` 또는 `var_lag_aic`)               |
| `irf_peak_horizon`                                                                  | IRF 피크 도달 시점 (개월)                                                                    |
| `irf_peak_magnitude`                                                                | IRF 피크 크기 (탄력성)                                                                       |

### `phase6_summary.csv`

| 컬럼                 | 타입 | 설명                                  |
| -------------------- | ---- | ------------------------------------- |
| `commodity_id`       | str  | 품목 식별자                           |
| `segment`            | str  | 분석 구간                             |
| `n_obs`              | int  | 전이율 유효 관측치 수                 |
| `n_breakpoints`      | int  | Bai-Perron 탐지 변화점 수             |
| `bp_dates`           | str  | 변화 시점 목록 (문자열 표현)          |
| `n_subperiods`       | int  | 독립 하위 기간 수                     |
| `borderline`         | bool | 경계 사례 플래그                      |
| `chow_2008_sig`      | bool | Chow 2008 유의 여부. 범위 밖이면 빈값 |
| `chow_2020_sig`      | bool | Chow 2020 유의 여부. 범위 밖이면 빈값 |
| `chow_2022_sig`      | bool | Chow 2022 유의 여부. 범위 밖이면 빈값 |
| `reestimation_count` | int  | 하위 기간 재추정 성공 수              |

### `breakpoints/{cid}_{seg}_breakpoints.json` → DB 적재 변환 규칙 (D-07)

| JSON 필드                              | DB 컬럼                                                        | 변환 규칙                                                                                 |
| -------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `borderline_cointegration`             | `breakpoints.borderline_cointegration`                         | 직접 매핑 (BOOLEAN)                                                                       |
| `bai_perron_breakpoints` (문자열 배열) | `breakpoints.bp_dates` (DATE[])                                | `"YYYY-MM"` → `"YYYY-MM-01"` 월초 승격                                                    |
| `bai_perron_best_k`                    | `breakpoints.bp_best_k`                                        | 직접 매핑 (INTEGER)                                                                       |
| `bic_scores`                           | `breakpoints.bic_scores` (JSONB)                               | 직접 매핑                                                                                 |
| `chow_test_points["2008-01"].*`        | `breakpoints.chow_2008_f`, `chow_2008_pvalue`, `chow_2008_sig` | 키 직접 매핑 (항상 존재)                                                                  |
| `chow_test_points["2020-01"].*`        | `breakpoints.chow_2020_f`, `chow_2020_pvalue`, `chow_2020_sig` | 키 직접 매핑 (항상 존재)                                                                  |
| `chow_test_points["2022-01"].*`        | `breakpoints.chow_2022_f`, `chow_2022_pvalue`, `chow_2022_sig` | 키 직접 매핑 (항상 존재)                                                                  |
| `subperiods[].start`, `.end`           | `subperiods.period_start`, `period_end`                        | `"YYYY-MM"` → `"YYYY-MM-01"` 월초 승격                                                    |
| `subperiods[].merged_with`             | `subperiods.merged_with_index`                                 | `merged_with` 값은 `id`가 아닌 `subperiod_index` 기준. 적재 시 `id` → `index` 재매핑 필요 |

---

## Phase 7 — 이상 패턴 탐지 (통계 기반, 주 방법론)

**입력**: `phase1/changes/{cid}_changes.csv`, `phase4/baseline/{cid}_{seg}_baseline.json`, `phase4/ect/{cid}_{seg}_ect.csv`, `phase6/breakpoints/{cid}_{seg}_breakpoints.json`, `phase6/subperiod_models/{cid}_{seg}_subperiod_{n}_model.json`

**방법**: 롤링 윈도우 W=48개월 기준. 초기 48개월은 기준 분포 축적 기간 (탐지 미수행). 로버스트니스 체크용으로 W=36, 60 병행 산출. 방향 역전은 상류/하류 양쪽 절대값 >= 1.0% 조건 부여. 전이율 산출 시 상류 절대값 < 0.5%이면 NaN 처리.

### 구간별 패턴 적용 범위

| 구간 | 패턴 1 | 패턴 2 | 패턴 3 | 비대칭 검정 |
| ---- | :----: | :----: | :----: | :---------: |
| A    |   ✔    |   ✔    |   —    |      ✔      |
| B    |   ✔    |   ✔    |   ✔    |      ✔      |
| C    |   ✔    |   —    |   —    |      —      |
| D    |   ✔    |   —    |   —    |      —      |
| D′   |   ✔    |   —    |   —    |      —      |

비대칭 검정: 공적분 있음 → TECM (α⁺/α⁻ Wald 검정), 공적분 없음 → 비대칭 VAR (더미 교차항).

**비대칭 검정 기간 범위 (D-01 확정)**: 비대칭 검정은 **전체 기간 단위 1회만 수행**한다. 구조 변화로 하위 기간이 분할되더라도 하위 기간별 비대칭 검정은 수행하지 않는다. 따라서 `pattern2_asymmetry.csv`에 `subperiod_id` 컬럼은 존재하지 않으며, DB `asymmetry_results.subperiod_id` 컬럼은 항상 NULL로 저장된다.

### 출력 디렉토리

```
data/processed/phase7/
├── pattern1/
│   ├── {cid}_{seg}_pattern1.csv           ← 방향 역전·시차 이탈 탐지 결과
│   └── pattern1_summary_stats.csv         ← 패턴 1 요약 통계
├── pattern2/
│   ├── {cid}_{seg}_pattern2_zscore.csv    ← 전이율 Z-score + IQR 탐지 결과
│   ├── {cid}_{seg}_pattern2_asymmetry.csv ← 비대칭 검정 결과 (구간 A·B만, 전체 기간)
│   └── pattern2_summary_stats.csv         ← 패턴 2 요약 통계
├── pattern3/
│   ├── {cid}_{seg}_pattern3.csv           ← 스프레드 누적 확대 탐지 결과 (구간 B만)
│   └── pattern3_summary_stats.csv         ← 패턴 3 요약 통계
├── robustness/
│   └── {cid}_{seg}_robustness_W{36|60}.csv  ← 롤링 윈도우 민감도 비교
├── stat_timeseries/
│   └── {cid}_{seg}_stat_timeseries.csv    ← DB stat_timeseries 테이블 적재용 전 시점 시계열
└── phase7_summary.csv                     ← 전 품목·구간 탐지 이벤트 목록
```

### `pattern1/{cid}_{seg}_pattern1.csv`

패턴 1 (방향 역전·시차 이탈) 탐지 결과. 전 구간 공통.

| 컬럼                 | 타입               | 설명                                                                |
| -------------------- | ------------------ | ------------------------------------------------------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일                                                           |
| `commodity_id`       | str                | 품목 식별자                                                         |
| `segment`            | str                | 분석 구간                                                           |
| `upstream_pct`       | float              | 상류 가격 변화율 (%)                                                |
| `downstream_pct`     | float              | 하류 가격 변화율 (%)                                                |
| `direction_reversal` | bool               | 방향 역전 여부 (상·하류 부호 불일치, 양쪽 절대값 >= 1.0% 조건)      |
| `upstream_move_date` | date \| None       | 시차 이탈 탐지 시 상류 변동 기준 월                                 |
| `lag_elapsed`        | int \| None        | 상류 변동 후 경과 기간 (개월)                                       |
| `normal_lag`         | int                | 기준선 정상 전달 시차 (IRF 피크 기준, 하위 기간별 상이)             |
| `lag_deviation`      | bool               | 시차 이탈 여부 (경과 > 정상 시차 + 1)                               |
| `insufficient_data`  | bool               | 관측 기간 종료로 인한 판정 유보                                     |
| `subperiod_id`       | int \| None        | 해당 시점의 하위 기간 ID (구조 변화 없는 구간이면 null)             |
| `pattern1_flag`      | bool               | 패턴 1 최종 탐지 여부 (방향 역전 OR 시차 이탈)                      |
| `flag_type`          | str \| None        | `"direction_reversal"` \| `"lag_deviation"` \| `"both"` \| `"none"` |

**비고 (D-05)**: `flag_type`은 DB `anomaly_results.pattern1_flag_type VARCHAR(20)` 컬럼에 그대로 보존된다. `direction_reversal`과 `lag_deviation` boolean 조합으로의 재변환은 적재 로직이 아닌 향후 확장 시에만 고려한다.

**비고 (D-14)**: `normal_lag`은 구조 변화가 탐지된 구간에서 SubperiodResolver에 의해 하위 기간별 상이한 값이 적용된다. 동일 품목·구간이라도 시기에 따라 정상 시차 기준이 달라진다.

### `pattern2/{cid}_{seg}_pattern2_zscore.csv`

패턴 2 전이율 크기 이탈 탐지 결과. 구간 A·B만 산출.

| 컬럼                     | 타입               | 설명                                                         |
| ------------------------ | ------------------ | ------------------------------------------------------------ |
| `date`                   | DatetimeIndex (MS) | 월 기준일                                                    |
| `commodity_id`           | str                | 품목 식별자                                                  |
| `segment`                | str                | 분석 구간                                                    |
| `upstream_pct`           | float              | 상류 가격 변화율 (%)                                         |
| `downstream_pct`         | float              | 하류 가격 변화율 (%)                                         |
| `transmission_rate`      | float              | 월별 전이율 = 하류 변화율 ÷ 상류 변화율 (상류 < 0.5% 시 NaN) |
| `rolling_mean`           | float              | 롤링 48개월 평균 전이율                                      |
| `rolling_std`            | float              | 롤링 48개월 표준편차                                         |
| `zscore`                 | float              | Z-score = (전이율 - rolling_mean) / rolling_std              |
| `q1`, `q3`, `iqr`        | float              | 롤링 IQR 통계                                                |
| `iqr_lower`, `iqr_upper` | float              | Tukey 이상치 경계 (Q1 - 1.5×IQR, Q3 + 1.5×IQR)               |
| `zscore_warning`         | bool               | Z-score > 2.0 (주의 레벨)                                    |
| `zscore_alert`           | bool               | Z-score > 2.5 (경보 레벨)                                    |
| `iqr_outlier`            | bool               | IQR 경계 이탈 여부                                           |
| `pattern2_flag`          | bool               | 패턴 2 최종 탐지 여부 (Z-score 경보 AND IQR 이탈 동시 충족)  |
| `over_transmission`      | bool               | 전이율 상한 초과 (과대 전달)                                 |
| `under_transmission`     | bool               | 전이율 하한 미달 (과소 전달)                                 |
| `in_warmup_period`       | bool               | 초기 48개월 기준 분포 축적 기간 여부 (탐지 미수행)           |

**비고 (D-03)**: `zscore_warning`(Z>2.0)과 `zscore_alert`(Z>2.5) 두 컬럼 모두 파이프라인에서 산출되며, DB `anomaly_results.zscore_warning BOOLEAN`과 `anomaly_results.zscore_alert BOOLEAN`에 각각 저장된다. API 응답의 `stat_metrics.zscore_threshold_warning: 2.0`은 임계값 상수이며, 해당 월의 warning 여부는 DB 저장값(`zscore_warning`)을 사용한다.

### `pattern2/{cid}_{seg}_pattern2_asymmetry.csv`

패턴 2 비대칭 전달 (로켓-깃털 효과) 검정 결과. 구간 A·B, **전체 기간 단위 1회 산출** (하위 기간별 검정 미수행).

| 컬럼                       | 타입          | 설명                                                       |
| -------------------------- | ------------- | ---------------------------------------------------------- |
| `commodity_id`             | str           | 품목 식별자                                                |
| `segment`                  | str           | 분석 구간                                                  |
| `model_type`               | str           | `"TECM"` (공적분 있음) \| `"asymmetric_VAR"` (공적분 없음) |
| `alpha_plus`               | float \| None | TECM 상승 국면 조정 계수 α⁺                                |
| `alpha_minus`              | float \| None | TECM 하락 국면 조정 계수 α⁻                                |
| `wald_stat`                | float \| None | Wald 검정 통계량 (H₀: α⁺ = α⁻)                             |
| `wald_pvalue`              | float \| None | Wald 검정 p값                                              |
| `asymmetry_significant`    | bool          | 비대칭 유의 여부 (p < 0.05)                                |
| `rocket_feather_direction` | str \| None   | 유의 시 방향 (`upward_stronger` \| `downward_stronger`)    |
| `up_coef`                  | float \| None | 비대칭 VAR 상승기 전이 계수                                |
| `down_coef`                | float \| None | 비대칭 VAR 하락기 전이 계수                                |
| `mean_tr_up`               | float         | 상승기 평균 전이율 (보조 지표)                             |
| `mean_tr_down`             | float         | 하락기 평균 전이율 (보조 지표)                             |
| `n_up`                     | int           | 상승기 관측 수                                             |
| `n_down`                   | int           | 하락기 관측 수                                             |

### `pattern3/{cid}_{seg}_pattern3.csv`

패턴 3 (국제가 안정기 중 하류 스프레드 누적 확대) 탐지 결과. 구간 B만 산출.

| 컬럼                | 타입               | 설명                                                       |
| ------------------- | ------------------ | ---------------------------------------------------------- |
| `date`              | DatetimeIndex (MS) | 월 기준일                                                  |
| `commodity_id`      | str                | 품목 식별자                                                |
| `segment`           | str                | 분석 구간                                                  |
| `intl_pct_change`   | float              | 국제가 원화 환산 월 변화율 (±3% 이내를 안정 구간으로 정의) |
| `in_stable_period`  | bool               | 국제가 안정 구간 여부 (abs(intl_pct_change) ≤ 0.03)        |
| `ect_or_spread`     | float              | ECT 값 (VECM) 또는 log 수준 스프레드 (VAR)                 |
| `ect_type`          | str                | `"ECT"` (VECM) \| `"log_spread"` (VAR)                     |
| `ect_abs`           | float              | ECT/스프레드 절대값                                        |
| `ect_sign`          | float              | ECT/스프레드 부호 (+1 / -1)                                |
| `abs_expanding`     | bool               | 직전 대비 절대값 확대 여부                                 |
| `same_sign_streak`  | int                | 같은 부호 유지 연속 개월 수                                |
| `abs_expand_streak` | int                | 같은 부호 + 절대값 확대 연속 개월 수                       |
| `pattern3_flag_n2`  | bool               | N=2 기준 탐지 여부 (조기 신호)                             |
| `pattern3_flag_n3`  | bool               | N=3 기준 탐지 여부 (기본)                                  |
| `pattern3_flag_n6`  | bool               | N=6 기준 탐지 여부 (구조적)                                |
| `pattern3_flag`     | bool               | 기본 탐지 여부 (`pattern3_flag_n3`와 동일)                 |

### `stat_timeseries/{cid}_{seg}_stat_timeseries.csv`

DB `stat_timeseries` 테이블 적재용 전 시점 시계열. 33개 구간 전부 산출.

| 컬럼                     | 타입               | 설명                              |
| ------------------------ | ------------------ | --------------------------------- |
| `commodity_id`           | str                | 품목 식별자                       |
| `segment_id`             | str                | 분석 구간                         |
| `period`                 | DatetimeIndex (MS) | 월 기준일                         |
| `transmission_rate`      | float              | 전이율 (상류 < 0.5% 시 NaN)       |
| `upstream_pct`           | float              | 상류 변화율 (%)                   |
| `downstream_pct`         | float              | 하류 변화율 (%)                   |
| `rolling_mean`           | float              | 롤링 평균 (A/B 구간만, 그 외 NaN) |
| `rolling_std`            | float              | 롤링 표준편차 (A/B 구간만)        |
| `zscore`                 | float              | Z-score (A/B 구간만)              |
| `q1`, `q3`, `iqr`        | float              | 사분위수, IQR (A/B 구간만)        |
| `iqr_lower`, `iqr_upper` | float              | IQR 경계 (A/B 구간만)             |
| `in_warmup_period`       | bool               | warmup 기간 여부                  |
| `zscore_w36`             | float              | W=36 Z-score (A/B 구간만)         |
| `zscore_w60`             | float              | W=60 Z-score (A/B 구간만)         |
| `ect_or_spread`          | float              | ECT 또는 로그 스프레드            |
| `ect_type`               | str                | `"ECT"` \| `"log_spread"`         |
| `in_stable_period`       | bool               | 안정 구간 (B 구간만, 그 외 NaN)   |
| `spread_n2`              | bool               | 스프레드 N=2 판정 (B 구간만)      |
| `spread_n3`              | bool               | 스프레드 N=3 판정 (B 구간만)      |
| `spread_n6`              | bool               | 스프레드 N=6 판정 (B 구간만)      |
| `exchange_rate_pct`      | float              | 환율 변화율 (%)                   |
| `intl_price_usd_pct`     | float              | 달러 국제가 변화율 (%)            |

### `phase7_summary.csv`

Phase 7 전 품목·구간 탐지 이벤트 통합 목록. Phase 7-ML 교차 대조 및 Phase 8 신뢰도 등급화 입력.

**동월·동구간 복수 패턴 집계 규칙 (D-13)**: 동일 품목·구간·월에 패턴 1과 패턴 2가 동시 탐지되더라도 **1개 행**으로 집계한다. `pattern_type`에는 대표 패턴(심각도 기준: pattern2 > pattern1 > pattern3), `pattern_types_all`에는 전체 패턴 목록을 저장한다. DB `anomaly_results` UNIQUE 제약 `(commodity_id, segment_id, period)`에 대응한다.

| 컬럼                | 타입 | 설명                                                           |
| ------------------- | ---- | -------------------------------------------------------------- |
| `commodity_id`      | str  | 품목 식별자                                                    |
| `segment`           | str  | 분석 구간                                                      |
| `date`              | date | 탐지 월 (YYYY-MM-01)                                           |
| `pattern_type`      | str  | 대표 패턴 (`"pattern1"` \| `"pattern2"` \| `"pattern3"`)       |
| `pattern_types_all` | str  | 탐지된 전체 패턴 목록 (콤마 구분, 예: `"pattern1,pattern2"`)   |
| `flag_detail`       | str  | 세부 탐지 유형 (예: `direction_reversal`, `over_transmission`) |
| `stat_detected`     | bool | 통계 기반 탐지 여부 (True 고정, 이 파일은 통계 탐지만 기록)    |

---

## Phase 7-ML — ML 보조 교차검증 (이상 탐지)

**입력**: `phase1/changes/{cid}_changes.csv` (상류·하류 변화율), `phase4/ect/{cid}_{seg}_ect.csv` (ECT/로그 스프레드), `phase4/baseline/{cid}_{seg}_baseline.json` (전이율 산출 기준)

**적용 구간**: 구간 A·B 한정 (전 품목 공통). 구간 C·D·D′ 미적용.

**ML 모델 학습 단위 (D-14)**: **품목×구간 단위 개별 학습**. 각 `{cid}_{seg}` 조합별로 독립적인 Isolation Forest, LOF, One-Class SVM 모델을 학습한다. `contamination` / `nu` 파라미터는 **0.08로 확정**하였으며, 민감도 분석(0.05, 0.10, 0.15)은 5축 평가 프레임워크의 축 4에서 품목·구간 공통 설정으로 수행한다.

**피처 6종 (고정, 8회 실험을 통해 최적 확인)**:

| #   | 피처명               | 설명                                    | 출처    |
| --- | -------------------- | --------------------------------------- | ------- |
| F1  | `transmission_rate`  | 월별 전이율 (하류 변화율 ÷ 상류 변화율) | Phase 4 |
| F2  | `upstream_pct`       | 상류 가격 변화율 (%)                    | Phase 1 |
| F3  | `downstream_pct`     | 하류 가격 변화율 (%)                    | Phase 1 |
| F4  | `ect_or_spread`      | ECT 또는 로그 수준 스프레드             | Phase 4 |
| F5  | `exchange_rate_pct`  | 환율 월 변동률 (%)                      | Phase 1 |
| F6  | `intl_price_usd_pct` | 달러 국제가 월 변동률 (%)               | Phase 1 |

**비고**: Phase 7 통계 판정 결과(Z-score 경보 여부 등)는 피처에서 제외 (순환 논리 방지).

**모델 파라미터 (최종 확정)**:

| 모델             | 파라미터            | 값                                     |
| ---------------- | ------------------- | -------------------------------------- |
| Isolation Forest | n_estimators        | 100                                    |
|                  | contamination       | 0.08                                   |
|                  | random_state        | 42                                     |
| LOF              | n_neighbors         | 10                                     |
|                  | contamination       | 0.08                                   |
|                  | novelty             | False                                  |
| One-Class SVM    | kernel              | rbf                                    |
|                  | nu                  | 0.08                                   |
|                  | gamma               | scale                                  |
| 전처리           | scaler              | StandardScaler                         |
| 앙상블           | consensus_threshold | 2 (3종 중 2개 이상 → ml_detected=True) |

### 코드 구조

```
src/preprocessing/Phase7/
├── phase7_ml_common.py     ← 피처 행렬 구성, 전처리(StandardScaler), stat_detected 조인
├── phase7_ml_models.py     ← 3종 모델 실행 + 앙상블 집계
├── phase7_ml_cross.py      ← 통계-ML 교차 대조 + 신뢰도 등급화
└── phase7_ml_run.py        ← 전체 파이프라인 진입점 (20유닛 순차 실행)
```

### 실행 방법

```bash
python src/preprocessing/Phase7/phase7_ml_run.py
```

### 출력 디렉토리

```
data/processed/phase7_ml/
├── features/
│   └── {cid}_{seg}_features.csv              ← ML 입력 피처 (스케일링 전)
├── predictions/
│   └── {cid}_{seg}_ml_predictions.csv        ← 3개 모델 탐지 결과 + 앙상블
├── cross_validation/
│   └── {cid}_{seg}_cross_val.csv             ← 통계-ML 교차 대조 결과
├── confidence_grades/
│   └── {cid}_{seg}_grades.csv                ← 신뢰도 등급 최종 산출 ← Phase 8 입력
├── models/{YYYYMMDD_HHMM}/
│   ├── {cid}_{seg}_if_{run_date}.pkl         ← Isolation Forest 모델
│   ├── {cid}_{seg}_lof_{run_date}.pkl        ← LOF 모델
│   ├── {cid}_{seg}_svm_{run_date}.pkl        ← One-Class SVM 모델
│   ├── {cid}_{seg}_scaler_{run_date}.pkl     ← StandardScaler 객체
│   └── run_log_{run_date}.json               ← 실행 파라미터·결과 로그
└── phase7_ml_summary.csv                     ← 전체 20유닛 요약 통계
```

### `features/{cid}_{seg}_features.csv`

| 컬럼                 | 타입               | 설명                        |
| -------------------- | ------------------ | --------------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일                   |
| `commodity_id`       | str                | 품목 ID                     |
| `segment`            | str                | 구간 (A 또는 B)             |
| `transmission_rate`  | float              | 월별 전이율                 |
| `upstream_pct`       | float              | 상류 가격 변화율 (%)        |
| `downstream_pct`     | float              | 하류 가격 변화율 (%)        |
| `ect_or_spread`      | float              | ECT 또는 로그 수준 스프레드 |
| `exchange_rate_pct`  | float              | 환율 월 변동률 (%)          |
| `intl_price_usd_pct` | float              | 달러 국제가 월 변동률 (%)   |

### `predictions/{cid}_{seg}_ml_predictions.csv`

| 컬럼                 | 타입               | 설명                                            |
| -------------------- | ------------------ | ----------------------------------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일                                       |
| `commodity_id`       | str                | 품목 ID                                         |
| `segment`            | str                | 구간 (A 또는 B)                                 |
| `if_anomaly`         | bool               | Isolation Forest 이상 탐지 여부                 |
| `if_score`           | float              | Isolation Forest 이상 점수 (낮을수록 이상)      |
| `lof_anomaly`        | bool               | LOF 이상 탐지 여부                              |
| `lof_score`          | float              | LOF 이상 점수 (낮을수록 이상)                   |
| `svm_anomaly`        | bool               | One-Class SVM 이상 탐지 여부                    |
| `svm_score`          | float              | SVM 결정 함수 값 (음수=이상)                    |
| `ml_consensus_count` | int                | 탐지 모델 수 (0~3)                              |
| `ml_detected`        | bool               | 3개 모델 중 2개 이상 탐지 시 True (앙상블 기준) |

### `cross_validation/{cid}_{seg}_cross_val.csv`

| 컬럼                 | 타입               | 설명                                              |
| -------------------- | ------------------ | ------------------------------------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일                                         |
| `commodity_id`       | str                | 품목 ID                                           |
| `segment`            | str                | 구간 (A 또는 B)                                   |
| `ml_detected`        | bool               | Phase 7-ML 앙상블 탐지 여부                       |
| `ml_consensus_count` | int                | 탐지 모델 수 (0~3)                                |
| `stat_detected`      | bool               | Phase 7 통계 기반 탐지 여부                       |
| `pattern_type`       | str \| None        | 통계 탐지된 패턴 유형 (stat_detected=True인 경우) |
| `agreement`          | bool               | 통계·ML 일치 여부                                 |

### `confidence_grades/{cid}_{seg}_grades.csv`

신청서 기준 3단계 신뢰도 등급 최종 산출. Phase 8 집계 입력.

**DB 적재 규칙 (D-02)**: `confidence_grade IS NOT NULL` 행, 즉 탐지된 행만 `anomaly_results` 테이블에 적재한다. `confidence_grade = null`인 정상 월은 적재하지 않는다. DB `anomaly_results`는 탐지 이벤트만 저장하는 테이블임을 명시한다.

| 컬럼                 | 타입               | 설명                |
| -------------------- | ------------------ | ------------------- |
| `date`               | DatetimeIndex (MS) | 월 기준일           |
| `commodity_id`       | str                | 품목 ID             |
| `segment`            | str                | 구간 (A 또는 B)     |
| `ml_detected`        | bool               | ML 탐지 여부        |
| `ml_consensus_count` | int                | 탐지 모델 수 (0~3)  |
| `stat_detected`      | bool               | 통계 기반 탐지 여부 |
| `pattern_type`       | str \| None        | 탐지된 패턴 유형    |
| `agreement`          | bool               | 통계·ML 일치 여부   |
| `confidence_grade`   | str                | 신뢰도 등급         |

`confidence_grade` 값:

| 등급          | 조건          | 설명                         |
| ------------- | ------------- | ---------------------------- |
| `"high"`      | 통계 ✔ + ML ✔ | 고신뢰: 통계·ML 동시 확인    |
| `"medium"`    | 통계 ✔ + ML ✗ | 중신뢰: 통계 확인, ML 미탐지 |
| `"reference"` | 통계 ✗ + ML ✔ | 참고: ML 탐지, 통계 미탐지   |
| `null`        | 통계 ✗ + ML ✗ | 정상 — DB 적재 제외          |

### `models/{YYYYMMDD_HHMM}/`

실행마다 타임스탬프 디렉토리를 생성하여 학습된 모델과 실행 로그를 버전 관리한다.

| 파일 패턴                           | 설명                                  |
| ----------------------------------- | ------------------------------------- |
| `{cid}_{seg}_if_{run_date}.pkl`     | Isolation Forest 모델 (joblib 직렬화) |
| `{cid}_{seg}_lof_{run_date}.pkl`    | LOF 모델                              |
| `{cid}_{seg}_svm_{run_date}.pkl`    | One-Class SVM 모델                    |
| `{cid}_{seg}_scaler_{run_date}.pkl` | StandardScaler 객체 (재현용)          |
| `run_log_{run_date}.json`           | 파라미터, 결과 요약, pkl 파일 목록    |

### `phase7_ml_summary.csv`

| 컬럼              | 타입 | 설명                    |
| ----------------- | ---- | ----------------------- |
| `commodity_id`    | str  | 품목 ID                 |
| `segment`         | str  | 구간                    |
| `total_months`    | int  | 전체 관측 월 수         |
| `valid_months`    | int  | 결측 제거 후 유효 월 수 |
| `dropped_months`  | int  | 결측으로 제외된 월 수   |
| `if_anomaly`      | int  | IF 탐지 건수            |
| `lof_anomaly`     | int  | LOF 탐지 건수           |
| `svm_anomaly`     | int  | SVM 탐지 건수           |
| `ml_detected`     | int  | 앙상블 탐지 건수        |
| `grade_high`      | int  | high 등급 건수          |
| `grade_medium`    | int  | medium 등급 건수        |
| `grade_reference` | int  | reference 등급 건수     |

---

### 5축 평가 프레임워크

ML 모델에 라벨이 없으므로 전통적 정확도/재현율을 산출할 수 없다. 대신 5개 독립 축으로 신뢰성을 다면 평가한다. 평가 코드는 `tests/phase7_ml/`에 위치하며, 실행마다 타임스탬프 디렉토리(`results/run_{YYYYMMDD_HHMMSS}/`)에 결과를 보존한다.

```bash
python tests/phase7_ml/run_all_evaluation.py --memo "실행 메모"
python tests/phase7_ml/generate_dashboard.py
```

**평가 코드 구조**:

```
tests/phase7_ml/
├── eval_common.py              ← 외부 충격 목록(5개 이벤트), 공통 유틸
├── test_axis1_esr.py           ← 축 1: 외부 충격 회수율 (ESR)
├── test_axis2_separation.py    ← 축 2: 이상 점수 분리도 (SR)
├── test_axis3_auc.py           ← 축 3: AUC + ROC curve (연속형 앙상블 스코어)
├── test_axis4_sensitivity.py   ← 축 4: 파라미터 민감도 (Stability Ratio)
├── test_axis5_consensus.py     ← 축 5: 합의 지표 (CTA + ASC + P_stat + P_ml)
├── run_all_evaluation.py       ← 5축 통합 실행 + 타임스탬프 저장 + run_meta.json
├── generate_dashboard.py       ← 5축 대시보드 HTML 생성
└── results/
    ├── run_{YYYYMMDD_HHMMSS}/  ← 축별 CSV + ROC curves JSON + run_meta.json
    └── latest/                 ← 최신 결과 복사본
```

**평가 출력 파일**:

| 파일                    | 설명                                          |
| ----------------------- | --------------------------------------------- |
| `axis1_esr.csv`         | 유닛별 모델별 ESR + 충격 건수                 |
| `axis2_separation.csv`  | 유닛별 모델별 분리도(SR)                      |
| `axis3_auc.csv`         | 유닛별 모델별 + 앙상블 AUC                    |
| `axis3_roc_curves.json` | 유닛별 FPR/TPR 배열 (ROC curve 대시보드용)    |
| `axis4_sensitivity.csv` | 유닛별 contamination SR + LOF k SR            |
| `axis5_consensus.csv`   | 유닛별 CTA, ASC, P_stat, P_ml, 가설 성립 여부 |
| `run_meta.json`         | 파라미터, 피처 목록, 요약 지표, 메모, status  |

**축 3 앙상블 AUC 산출 방식**: `ml_consensus_count`(0~3 이산값) 대신, 3종 모델의 원시 이상 점수를 부호 반전 → Min-Max 정규화 → 평균하여 연속형 스코어를 사용한다. 이에 따라 ROC curve가 계단형이 아닌 부드러운 곡선으로 산출된다.

---

### SHAP 피처 중요도 분석

3종 모델에 SHAP(SHapley Additive exPlanations)를 적용하여 각 모델의 피처별 기여도를 정량화한다. 모델별 독립 코드로 관리하며, `--output-dir` 인자로 중단 후 이어하기를 지원한다.

```bash
python tests/shap/run_shap_if.py                          # IF (TreeExplainer, 수 초)
python tests/shap/run_shap_lof.py                         # LOF (KernelExplainer, ~5분)
python tests/shap/run_shap_svm.py                         # SVM (KernelExplainer, ~4분)
python tests/shap/generate_shap_dashboard.py \
  --if-dir {IF_DIR} --lof-dir {LOF_DIR} --svm-dir {SVM_DIR}
```

**SHAP 코드 구조**:

```
tests/shap/
├── run_shap_if.py              ← IF SHAP (TreeExplainer, exact)
├── run_shap_lof.py             ← LOF SHAP (KernelExplainer, novelty=True 래퍼)
├── run_shap_svm.py             ← SVM SHAP (KernelExplainer, -decision_function)
├── generate_shap_dashboard.py  ← Bar Plot + Heatmap + Beeswarm 대시보드 생성
└── results/
    ├── {YYYYMMDD_HHMM}_IF/     ← IF SHAP 결과 (20개 CSV + summary + meta)
    ├── {YYYYMMDD_HHMM}_LOF/    ← LOF SHAP 결과
    ├── {YYYYMMDD_HHMM}_SVM/    ← SVM SHAP 결과
    └── 대시보드_{YYYYMMDD_HHMM}/ ← 대시보드 HTML + Beeswarm PNG ×3
```

**SHAP 출력 파일 (모델별)**:

| 파일                   | 설명                                                                |
| ---------------------- | ------------------------------------------------------------------- |
| `{cid}_{seg}_shap.csv` | 전체 관측치의 6종 피처별 SHAP 값 (date, commodity_id, segment 포함) |
| `shap_summary.csv`     | 유닛별 피처별 Mean \|SHAP\| + top 피처 + 중요도                     |
| `run_meta.json`        | Explainer 종류, status(complete/partial), 글로벌 피처 중요도        |

**SHAP run_meta.json 주요 필드**:

| 필드                        | 설명                                               |
| --------------------------- | -------------------------------------------------- |
| `model`                     | IF / LOF / SVM                                     |
| `explainer`                 | TreeExplainer (IF) 또는 KernelExplainer (LOF, SVM) |
| `status`                    | `"complete"` 또는 `"partial (n/20)"`               |
| `n_segments_complete`       | 완료된 유닛 수                                     |
| `n_segments_skipped`        | 이어하기로 스킵된 유닛 수                          |
| `background_data`           | `"full (no subsampling)"`                          |
| `global_feature_importance` | 6종 피처별 전체 유닛 평균 Mean \|SHAP\|            |

---

## 데이터 리니지 요약

```
[Phase 0] merged/{cid}.csv + product_config.json
    │
    ▼  Phase 1: STL 분해
phase1/seasonal_adjusted/{cid}_sa.csv     → Phase 2·3 입력 (수준 데이터)
phase1/changes/{cid}_changes.csv          → Phase 2·4·7·7-ML 입력 (변화율)
    │
    ▼  Phase 2: ADF+KPSS 병행 검정
phase2/integration_orders.json            → Phase 3 주 입력
    │
    ▼  Phase 3: Johansen 공적분 검정
phase3/model_routing.json                 → Phase 4·5 주 입력
    │
    ▼  Phase 4: VAR/VECM 추정 + IRF
phase4/baseline/{cid}_{seg}_baseline.json → Phase 7 기준선 참조 (warmup_end 포함)
phase4/irf/{cid}_{seg}_irf.csv            → Phase 7 패턴 1 시차 기준
phase4/ect/{cid}_{seg}_ect.csv            → Phase 7 패턴 3 · Phase 7-ML 피처
    │
    ├──▶  Phase 5 (4구간 품목 구간 C): Granger 인과 방향 확정
    │         → phase3/model_routing.json granger_direction 갱신
    │
    ▼  Phase 6: 구조 변화 탐지 (Chow Test 3 고정 시점 + Bai-Perron)
phase6/breakpoints/{cid}_{seg}_breakpoints.json → Phase 7 하위 기간 참조
    │
    ▼  Phase 7: 이상 패턴 탐지 (통계)
phase7/phase7_summary.csv                 → Phase 7-ML 교차 대조 입력
    │                                        (동월 복수 패턴 → 1행 집계)
    ▼  Phase 7-ML: ML 보조 교차검증 (품목×구간 단위 개별 학습)
phase7_ml/confidence_grades/{cid}_{seg}_grades.csv → Phase 8 신뢰도 집계 입력
                                                       (null=정상 행 적재 제외)
```

---

## 파라미터 기준값 요약

Phase 구현 시 `config/settings.py` 값을 우선 참조한다.

| 파라미터                  | 값                                | 설정 위치              |
| ------------------------- | --------------------------------- | ---------------------- |
| STL_PERIOD                | 12                                | settings.py            |
| STL_ROBUST                | True                              | settings.py            |
| ADF_SIGNIFICANCE          | 0.05                              | settings.py            |
| KPSS_SIGNIFICANCE         | 0.05                              | settings.py            |
| KPSS_REGRESSION           | `'c'`                             | phase2 코드 상수       |
| JOHANSEN_DET_ORDER        | 0                                 | settings.py            |
| LAG_SEARCH_RANGE          | range(1, 5)                       | settings.py            |
| ROLLING_WINDOW            | 48                                | settings.py            |
| ROLLING_WINDOW_ROBUSTNESS | [36, 48, 60]                      | settings.py            |
| ZSCORE_WARNING            | 2.0                               | settings.py            |
| ZSCORE_ALERT              | 2.5                               | settings.py            |
| IQR_MULTIPLIER            | 1.5                               | settings.py            |
| STABILITY_THRESHOLD       | 0.03                              | settings.py            |
| PATTERN3_N_VALUES         | [2, 3, 6]                         | settings.py            |
| MIN_SUBPERIOD_OBS         | 60                                | settings.py            |
| CHOW_TEST_POINTS          | ["2008-01", "2020-01", "2022-01"] | settings.py (고정 3개) |
| IF_N_ESTIMATORS           | 100                               | settings.py            |
| CONTAMINATION_RANGE       | [0.05, 0.10, 0.15]                | settings.py            |
| LOF_N_NEIGHBORS_RANGE     | range(5, 21)                      | settings.py            |
| SVM_KERNEL                | `'rbf'`                           | settings.py            |
| RANDOM_STATE              | 42                                | settings.py            |

---

_v7 — 당시 design_review v1 기반 갱신에서 출발, Phase 3·4·5·6 반영하여 갱신. Phase 3~7 출력 명세는 구현 착수 시 코드 기준으로 재갱신 필요. (v7에서 외부 참조 표기를 `abcd_vN.md` 규칙으로 전환, `docs/docs_manifest.md` 버전 해석기 연동)_

## Phase 8 — 결과 종합 및 로버스트니스 체크

**실행**: `python src/preprocessing/phase8/phase8_run.py`

**입력**: Phase 7 산출물 전체, Phase 7-ML 산출물 전체, Phase 4 baseline, Phase 6 breakpoints, Phase 1 changes/dummy_changes, product_config.json

**방법**: 집계·비교·대조 분석. 새 탐지 없음. R3(contamination 민감도)에서만 ML 3종 모델 재실행.

### 출력 디렉토리

```
data/processed/phase8/
├── summary/
│   ├── confidence_summary.csv              ← S1: 신뢰도 등급 집계
│   ├── agreement_analysis.csv              ← S2: 통계-ML 일치율
│   ├── cross_commodity_comparison.csv      ← S3: 품목 간 횡단 비교
│   ├── wholesale_comparison.csv            ← S4: 도매 그룹 비교
│   ├── wholesale_downstream_analysis.csv   ← S4: 도매 하류 전달 분석
│   ├── shock_correspondence.csv            ← S5: 외부 충격 요약
│   └── shock_detail.csv                    ← S5: 외부 충격 상세
├── robustness/
│   ├── rolling_window_sensitivity.csv      ← R1: 롤링 윈도우 민감도
│   ├── seasonal_method_comparison.csv      ← R2: 계절 조정 방식 비교
│   ├── contamination_sensitivity.csv       ← R3: contamination 민감도
│   └── robustness_summary.json             ← R1~R3 전체 요약
├── synchrony/
│   ├── heatmap_data.csv                    ← T1: 히트맵 데이터
│   ├── monthly_co_detection.csv            ← T2: 월별 동시 탐지
│   ├── case_A_ukraine.csv                  ← T3: 케이스 A
│   ├── case_B_russia_drought.csv           ← T4: 케이스 B
│   ├── case_C_feed_livestock.csv           ← T5: 케이스 C
│   └── ml_reference_co_occurrence.csv      ← T6: ML reference 동시 발생
└── phase8_meta.json                        ← 전체 실행 메타 정보
```

---

### `summary/confidence_summary.csv`

20개 유닛(A·B) + ALL 합계 행. 신뢰도 등급별 이상 이벤트 집계.

| 컬럼              | 타입  | 설명                                         |
| ----------------- | ----- | -------------------------------------------- |
| `commodity_id`    | str   | 품목 식별자 (ALL = 전체 합계)                |
| `segment`         | str   | 구간 (A / B / ALL)                           |
| `total_anomalies` | int   | 이상 이벤트 총수 (high + medium + reference) |
| `high`            | int   | 고신뢰: 통계 + ML 동시 탐지                  |
| `medium`          | int   | 중신뢰: 통계만 탐지                          |
| `reference`       | int   | 참고: ML만 탐지                              |
| `high_pct`        | float | high / total_anomalies × 100                 |
| `stat_only`       | int   | = medium                                     |
| `ml_only`         | int   | = reference                                  |

---

### `summary/agreement_analysis.csv`

20개 유닛. 통계-ML 4분류 교차 대조 및 Cohen's Kappa.

| 컬럼             | 타입  | 설명                                               |
| ---------------- | ----- | -------------------------------------------------- |
| `commodity_id`   | str   | 품목 식별자                                        |
| `segment`        | str   | 구간 (A / B)                                       |
| `total_months`   | int   | 전체 관측 월 수 (결측 제거 후)                     |
| `both_detected`  | int   | 통계 ✓ + ML ✓                                      |
| `stat_only`      | int   | 통계 ✓ + ML ✗                                      |
| `ml_only`        | int   | 통계 ✗ + ML ✓                                      |
| `both_normal`    | int   | 통계 ✗ + ML ✗                                      |
| `agreement_rate` | float | (both_detected + both_normal) / total_months × 100 |
| `cohen_kappa`    | float | Cohen's Kappa 계수 (-1 ~ 1)                        |

---

### `summary/cross_commodity_comparison.csv`

20개 유닛. 10개 품목 A·B 구간 패턴별 탐지 건수 및 탐지율.

| 컬럼              | 타입  | 설명                          |
| ----------------- | ----- | ----------------------------- |
| `commodity_id`    | str   | 품목 식별자                   |
| `segment`         | str   | 구간 (A / B)                  |
| `total_obs`       | int   | 전체 관측 수                  |
| `p1_count`        | int   | 패턴 1 탐지 건수              |
| `p1_rate`         | float | 패턴 1 탐지율 (%)             |
| `p2_count`        | int   | 패턴 2 탐지 건수              |
| `p2_rate`         | float | 패턴 2 탐지율 (%)             |
| `p3_count`        | int   | 패턴 3 탐지 건수 (B만, A는 0) |
| `p3_rate`         | float | 패턴 3 탐지율 (%)             |
| `total_stat`      | int   | 통계 탐지 총 건수             |
| `total_stat_rate` | float | 통계 탐지율 (%)               |
| `ml_detected`     | int   | ML 탐지 건수                  |
| `high_count`      | int   | 고신뢰 건수                   |
| `has_wholesale`   | bool  | 도매 단계 유무                |

---

### `summary/wholesale_comparison.csv`

2행. 3구간(7종) vs 4구간(3종) 그룹 비교.

| 컬럼              | 타입  | 설명                          |
| ----------------- | ----- | ----------------------------- |
| `group`           | str   | '3seg' / '4seg'               |
| `n_commodities`   | int   | 품목 수                       |
| `avg_p1_rate_A`   | float | 구간 A 평균 패턴 1 탐지율 (%) |
| `avg_p1_rate_B`   | float | 구간 B 평균 패턴 1 탐지율 (%) |
| `avg_p2_rate_A`   | float | 구간 A 평균 패턴 2 탐지율 (%) |
| `avg_p2_rate_B`   | float | 구간 B 평균 패턴 2 탐지율 (%) |
| `avg_stat_rate_A` | float | 구간 A 평균 전체 탐지율 (%)   |
| `avg_stat_rate_B` | float | 구간 B 평균 전체 탐지율 (%)   |
| `avg_high_pct`    | float | 평균 고신뢰 비율 (%)          |

---

### `summary/wholesale_downstream_analysis.csv`

6행 (3품목 × 2쌍). 4구간 품목의 도매 하류(C·D) 전달 분석.

| 컬럼                    | 타입  | 설명                                       |
| ----------------------- | ----- | ------------------------------------------ |
| `commodity_id`          | str   | 품목 식별자 (groundnuts / banana / orange) |
| `seg_pair`              | str   | 구간 쌍 ('A→C' / 'B→D')                    |
| `upstream_count`        | int   | 상류 구간 탐지 건수                        |
| `downstream_count`      | int   | 하류 구간 탐지 건수                        |
| `co_occurrence`         | int   | 동월 동시 탐지 건수                        |
| `co_occurrence_rate`    | float | 동시 탐지율 (%)                            |
| `downstream_follows_1m` | int   | 상류 탐지 후 1개월 내 하류 탐지 건수       |
| `downstream_follows_3m` | int   | 상류 탐지 후 3개월 내 하류 탐지 건수       |

---

### `summary/shock_correspondence.csv`

5행 (충격 5개). 외부 충격별 통계·ML 회수율 요약.

| 컬럼                          | 타입  | 설명                                          |
| ----------------------------- | ----- | --------------------------------------------- |
| `shock_id`                    | str   | 충격 ID (E1 / E2 / E4 / E6 / E9)              |
| `shock_name`                  | str   | 이벤트명                                      |
| `shock_start`                 | str   | 윈도우 시작 (YYYY-MM-DD)                      |
| `shock_end`                   | str   | 윈도우 종료 (YYYY-MM-DD)                      |
| `n_applicable_segments`       | int   | 적용 가능 유닛 수                             |
| `stat_hits`                   | int   | 통계 탐지가 윈도우 내 1건 이상 탐지한 유닛 수 |
| `stat_recall`                 | float | stat_hits / n_applicable_segments             |
| `ml_hits`                     | int   | ML 탐지가 윈도우 내 1건 이상 탐지한 유닛 수   |
| `ml_recall`                   | float | ml_hits / n_applicable_segments               |
| `high_hits`                   | int   | 고신뢰 탐지가 윈도우 내 존재하는 유닛 수      |
| `total_stat_events_in_window` | int   | 윈도우 내 통계 탐지 이벤트 총 건수            |
| `total_ml_events_in_window`   | int   | 윈도우 내 ML 탐지 이벤트 총 건수              |

---

### `summary/shock_detail.csv`

74행 (충격 × 유닛). 외부 충격별 유닛 상세.

| 컬럼                      | 타입 | 설명                              |
| ------------------------- | ---- | --------------------------------- |
| `shock_id`                | str  | 충격 ID                           |
| `commodity_id`            | str  | 품목 식별자                       |
| `segment`                 | str  | 구간 (A / B)                      |
| `stat_detected_in_window` | bool | 통계 탐지 존재 여부               |
| `ml_detected_in_window`   | bool | ML 탐지 존재 여부                 |
| `high_in_window`          | bool | 고신뢰 탐지 존재 여부             |
| `stat_event_count`        | int  | 통계 탐지 건수                    |
| `ml_event_count`          | int  | ML 탐지 건수                      |
| `pattern_types`           | str  | 탐지된 패턴 유형 목록 (쉼표 구분) |

---

### `robustness/rolling_window_sensitivity.csv`

20개 유닛. 패턴 2의 W=36/48/60 탐지 비교.

| 컬럼                | 타입  | 설명                                 |
| ------------------- | ----- | ------------------------------------ |
| `commodity_id`      | str   | 품목 식별자                          |
| `segment`           | str   | 구간 (A / B)                         |
| `w36_flags`         | int   | W=36 패턴 2 탐지 건수                |
| `w48_flags`         | int   | W=48 패턴 2 탐지 건수 (기본값)       |
| `w60_flags`         | int   | W=60 패턴 2 탐지 건수                |
| `w36_w48_overlap`   | int   | W36과 W48 동시 탐지 건수             |
| `w48_w60_overlap`   | int   | W48과 W60 동시 탐지 건수             |
| `w36_w48_jaccard`   | float | Jaccard 유사도 (0~1)                 |
| `w48_w60_jaccard`   | float | Jaccard 유사도 (0~1)                 |
| `stability_verdict` | str   | 판정 (stable / moderate / sensitive) |

**판정 기준**: Jaccard ≥ 0.7 → stable, 0.4~0.7 → moderate, < 0.4 → sensitive.

---

### `robustness/seasonal_method_comparison.csv`

20개 유닛. STL vs 계절 더미 기반 패턴 2 탐지 비교.

| 컬럼                | 타입  | 설명                                 |
| ------------------- | ----- | ------------------------------------ |
| `commodity_id`      | str   | 품목 식별자                          |
| `segment`           | str   | 구간 (A / B)                         |
| `stl_flags`         | int   | STL 기반 패턴 2 탐지 건수            |
| `dummy_flags`       | int   | 계절 더미 기반 패턴 2 탐지 건수      |
| `overlap`           | int   | 동시 탐지 건수                       |
| `jaccard`           | float | Jaccard 유사도 (0~1)                 |
| `stl_only`          | int   | STL에서만 탐지된 건수                |
| `dummy_only`        | int   | 더미에서만 탐지된 건수               |
| `stability_verdict` | str   | 판정 (stable / moderate / sensitive) |

**비고**: Phase 2~6은 재실행하지 않음. ECT·IRF·구조 변화는 STL 기반 결과를 공유.

---

### `robustness/contamination_sensitivity.csv`

20개 유닛. contamination 0.05/0.08/0.10/0.12/0.15 ML 재실행 결과.

| 컬럼                | 타입  | 설명                                  |
| ------------------- | ----- | ------------------------------------- |
| `commodity_id`      | str   | 품목 식별자                           |
| `segment`           | str   | 구간 (A / B)                          |
| `c005_detected`     | int   | contamination=0.05 탐지 건수          |
| `c008_detected`     | int   | contamination=0.08 탐지 건수 (기본값) |
| `c010_detected`     | int   | contamination=0.10 탐지 건수          |
| `c012_detected`     | int   | contamination=0.12 탐지 건수          |
| `c015_detected`     | int   | contamination=0.15 탐지 건수          |
| `c005_c008_jaccard` | float | 0.05 vs 0.08 Jaccard                  |
| `c010_c008_jaccard` | float | 0.10 vs 0.08 Jaccard                  |
| `c012_c008_jaccard` | float | 0.12 vs 0.08 Jaccard                  |
| `c015_c008_jaccard` | float | 0.15 vs 0.08 Jaccard                  |
| `stability_verdict` | str   | 판정 (stable / moderate / sensitive)  |

**비고**: stat_timeseries에서 6종 피처를 추출, 동일 StandardScaler + IF/LOF/SVM 재실행. 앙상블 기준 ≥ 2/3.

---

### `robustness/robustness_summary.json`

R1~R3 전체 요약.

```json
{
  "rolling_window": {
    "avg_jaccard_w36_w48": float,
    "avg_jaccard_w48_w60": float,
    "verdict": "stable | moderate | sensitive",
    "n_stable": int,
    "n_moderate": int,
    "n_sensitive": int
  },
  "seasonal_method": { ... },
  "contamination": {
    "per_pair_avg_jaccard": { "c005_c008_jaccard": float, ... },
    "overall_avg_jaccard": float,
    "verdict": "stable | moderate | sensitive",
    ...
  }
}
```

---

### `synchrony/heatmap_data.csv`

5,372행 (월 × 품목 × 구간). 시각화용 히트맵 원시 데이터.

| 컬럼               | 타입 | 설명                                  |
| ------------------ | ---- | ------------------------------------- |
| `date`             | date | 월 (YYYY-MM-01)                       |
| `commodity_id`     | str  | 품목 식별자                           |
| `segment`          | str  | 구간 (A / B)                          |
| `pattern_type`     | str  | pattern1 / pattern2 / pattern3 / none |
| `confidence_grade` | str  | high / medium / reference / none      |
| `stat_detected`    | bool | 통계 탐지 여부                        |
| `ml_detected`      | bool | ML 탐지 여부                          |

---

### `synchrony/monthly_co_detection.csv`

구간별 월 단위 동시 탐지 집계.

| 컬럼                  | 타입 | 설명                          |
| --------------------- | ---- | ----------------------------- |
| `date`                | date | 월 (YYYY-MM-01)               |
| `segment`             | str  | 구간 (A / B)                  |
| `n_commodities_stat`  | int  | 통계 탐지 품목 수 (0~10)      |
| `n_commodities_ml`    | int  | ML 탐지 품목 수 (0~10)        |
| `n_commodities_high`  | int  | 고신뢰 탐지 품목 수 (0~10)    |
| `commodity_list_stat` | str  | 탐지 품목 ID 목록 (쉼표 구분) |
| `in_shock_window`     | bool | 외부 충격 윈도우 내 여부      |
| `shock_id`            | str  | 해당 충격 ID (없으면 빈 값)   |

---

### `synchrony/case_A_ukraine.csv`

9행 (2022-02 ~ 2022-10). 케이스 A: wheat, maize, soybean 구간 A.

| 컬럼               | 타입 | 설명                                           |
| ------------------ | ---- | ---------------------------------------------- |
| `date`             | date | 월                                             |
| `{cid}_A_detected` | bool | 해당 품목 구간 A 탐지 여부                     |
| `{cid}_A_pattern`  | str  | 패턴 유형 (pattern1 / pattern2 / none)         |
| `{cid}_A_grade`    | str  | 신뢰도 등급 (high / medium / reference / none) |
| `n_simultaneous`   | int  | 동시 탐지 품목 수 (0~3)                        |

`{cid}`: wheat, maize, soybean

---

### `synchrony/case_B_russia_drought.csv`

11행 (2010-08 ~ 2011-06). 케이스 B: 7품목 구간 A.

case_A_ukraine.csv와 동일 구조. `{cid}`: wheat, maize, soybean, palmoil, sugar, coffee, beef. `n_simultaneous` 범위 0~7.

---

### `synchrony/case_C_feed_livestock.csv`

191행. 케이스 C: maize/soybean A 탐지 → beef A 시차 반응.

| 컬럼                        | 타입  | 설명                                         |
| --------------------------- | ----- | -------------------------------------------- |
| `trigger_date`              | date  | 트리거 날짜 (maize/soybean A 탐지 월)        |
| `trigger_commodity`         | str   | maize / soybean                              |
| `beef_A_response_1m`        | bool  | 1개월 내 소고기 A 탐지 여부                  |
| `beef_A_response_3m`        | bool  | 3개월 내 소고기 A 탐지 여부                  |
| `beef_A_response_6m`        | bool  | 6개월 내 소고기 A 탐지 여부                  |
| `beef_A_first_response_lag` | float | 최초 반응 시차 (개월, NaN = 6개월 내 미반응) |

**비고**: 반응은 누적. 1m 반응 시 3m·6m도 True. 탐색적 분석으로 인과관계를 의미하지 않음.

---

### `synchrony/ml_reference_co_occurrence.csv`

k ≥ 3인 월만 기록. ML 단독 탐지(reference)가 3개 이상 품목에서 동시 발생한 월.

| 컬럼              | 타입 | 설명                          |
| ----------------- | ---- | ----------------------------- |
| `date`            | date | 월 (YYYY-MM-01)               |
| `segment`         | str  | 구간 (A / B)                  |
| `n_reference`     | int  | reference 등급 품목 수 (≥ 3)  |
| `commodity_list`  | str  | 해당 품목 ID 목록 (쉼표 구분) |
| `in_shock_window` | bool | 외부 충격 윈도우 내 여부      |
| `shock_id`        | str  | 해당 충격 ID (없으면 빈 값)   |

---

### `phase8_meta.json`

전체 실행 메타 정보.

```json
{
  "run_timestamp": "YYYY-MM-DD HH:MM:SS",
  "elapsed_seconds": float,
  "modules": {
    "summary": { "outputs": ["confidence_summary.csv", ...] },
    "robustness": { "outputs": ["rolling_window_sensitivity.csv", ...] },
    "synchrony": { "outputs": ["heatmap_data.csv", ...] }
  },
  "key_findings": {
    "confidence": { "total_anomalies": int, "high": int, ... },
    "agreement": { "avg_agreement_rate": float, "avg_cohen_kappa": float },
    "shock_recall": { "E1": { "stat_recall": float, "ml_recall": float }, ... },
    "robustness": { "rolling_window": { "verdict": str }, ... },
    "feed_livestock_lag": { "n_triggers": int, "response_3m_pct": float, ... },
    "ml_reference_co_occurrence": { "k3_plus_months": int, "in_shock_window": int }
  }
}
```

---
