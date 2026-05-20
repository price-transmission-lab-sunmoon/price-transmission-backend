# Phase 1~2 — 계절 조정 및 정상성 검정

> **작성일**: 2026-04-15  
> **목적**: Phase 1(STL 계절 조정)과 Phase 2(ADF+KPSS 정상성 검정)의 목적, 코드 역할, 실행 방법, 결과 해석을 정리

---

## 1. 개요

Phase 1은 Phase 0 산출물(merged CSV)의 가격 시계열에서 계절 성분을 제거하고 변화율을 산출하는 단계이다. Phase 2는 계절 조정된 시계열의 정상성을 검정하여, Phase 3(공적분 검정)의 입력 형태를 확정하는 단계이다.

```
Phase 0 산출물 (merged CSV)
    │
    ▼
[Phase 1] 계절 조정
    ├─ STL 분해 → 계절 성분 제거 → 계절 조정 시계열 (_sa)
    ├─ 계절 조정 시계열에서 전월 대비 변화율 산출 (_pct)
    ├─ 외생 변수(환율, 달러 국제가) 변화율 산출
    └─ 로버스트니스 체크용 계절 더미 방식 병행 산출
    │
    ▼
[Phase 2] 정상성 검정
    ├─ ADF + KPSS 병행 검정
    ├─ 비정상 시 1차 차분 후 재검정
    └─ 품목·컬럼별 적분 차수 I(d) 확정
    │
    ▼
Phase 3 (Johansen 공적분 검정) 입력
```

---

## 2. 실행 방법

### 전제 조건

Phase 0이 완료되어 `data/processed/merged/` 내 품목별 CSV와 `data/processed/product_config.json`이 존재해야 한다.

### Phase 1 실행

```bash
python src/preprocessing/phase1_seasonal_adjustment.py
```

### Phase 2 실행

```bash
python src/preprocessing/phase2_stationarity_test.py
```

Phase 1 → Phase 2 순서로 실행한다. Phase 2는 Phase 1 산출물을 입력으로 사용한다.

---

## 3. Phase 1 — 계절 조정

### 3.1 목적

가격 시계열에는 계절적 패턴이 존재한다(예: 밀 수입단가의 수확기 하락, 바나나 도매가의 여름철 상승). 이 계절 성분을 제거하지 않으면 Phase 7의 이상 탐지에서 오탐이 발생할 수 있다. 예를 들어 국제가와 PPI의 계절 패턴이 다르면, 실제로는 정상적인 전달이지만 방향 역전(패턴 1)으로 오탐될 수 있다.

### 3.2 STL 분해 (Seasonal-Trend Decomposition using LOESS)

각 가격 시계열을 세 가지 성분으로 분리한다:

```
원 시계열 = 추세(Trend) + 계절(Seasonal) + 잔차(Residual)
계절 조정 시계열 = 원 시계열 - 계절 성분
```

STL 파라미터:

| 파라미터               | 값                 | 근거                                                        |
| ---------------------- | ------------------ | ----------------------------------------------------------- |
| period                 | 12                 | 월별 데이터 → 12개월 주기                                   |
| robust                 | True               | 이상치(2008·2022 급등)가 계절 추정을 오염시키지 않도록 보호 |
| seasonal, trend 윈도우 | statsmodels 기본값 | seasonal=7, trend=auto                                      |

사용 함수: `statsmodels.tsa.seasonal.STL`

### 3.3 처리 대상 컬럼

| 품목 유형        | STL 적용 대상 컬럼                                          |
| ---------------- | ----------------------------------------------------------- |
| 3구간 품목 (7종) | intl_price_krw, import_price_usd, ppi, cpi                  |
| 4구간 품목 (3종) | intl_price_krw, import_price_usd, ppi, cpi, wholesale_price |

exchange_rate와 intl_price_usd는 STL 미적용. Phase 7-ML 외생 피처용으로 원본에서 변화율만 산출한다.

### 3.4 변화율 산출

계절 조정 시계열에서 전월 대비 변화율(%)을 산출한다:

```
변화율 = (X_t - X_{t-1}) / X_{t-1} × 100
```

첫 행은 NaN (이전 월 부재). 이 변화율 데이터가 Phase 2~7의 주 입력이 된다.

### 3.5 로버스트니스 — 계절 더미 방식

Phase 8 로버스트니스 체크를 위해 월별 더미 변수 OLS 방식도 병행 산출한다:

```
y_t = α + Σ(β_m × D_m) + ε_t    (m = 2, ..., 12; 1월 기준)
계절 조정 = y_t - Σ(β_m × D_m)
```

Phase 8에서 STL 방식과 계절 더미 방식의 탐지 결과를 비교하여 "계절 조정 방법에 따라 결과가 달라지는가?"를 검증한다.

### 3.6 주요 발견

phase1_summary.csv에서 확인된 계절성 강도 (seasonal_pct_of_mean > 20%인 시계열):

- **계절성이 매우 강한 시계열**: 바나나 PPI(114%), 오렌지 PPI(114%), 바나나 intl_price_krw(66%), 오렌지 intl_price_krw(65%) — STL 계절 조정이 필수적인 품목
- **계절성이 중간인 시계열**: 대부분의 intl_price_krw 및 import_price_usd 컬럼 (20~56%)
- **계절성이 약한 시계열**: 대부분의 PPI·CPI 컬럼 (2~16%)

바나나·오렌지의 PPI가 114%로 극단적으로 높은 이유는 두 품목이 '과실류' 합산 PPI(404Y014)를 사용하기 때문이며, 과실류 전체의 계절 변동이 반영된 것이다.

---

## 4. Phase 2 — 정상성 검정

### 4.1 목적

시계열 분석(VAR/VECM)은 정상 시계열을 전제로 한다. 비정상 시계열을 그대로 사용하면 가성 회귀(spurious regression)가 발생하여 분석 결과가 무효가 된다. Phase 2에서 각 시계열의 정상성을 확인하고, 비정상 시 차분 적용 여부를 결정한다.

### 4.2 검정 방법 — ADF + KPSS 병행

두 검정의 귀무가설이 상호 보완적이므로 병행하여 판정 신뢰도를 높인다.

**ADF 검정 (Augmented Dickey-Fuller)**:

- 귀무가설: 단위근 존재 (비정상)
- p < 0.05 → 기각 → **정상**
- 사용 함수: `statsmodels.tsa.stattools.adfuller(autolag='AIC')`

**KPSS 검정 (Kwiatkowski-Phillips-Schmidt-Shin)**:

- 귀무가설: 정상
- p < 0.05 → 기각 → **비정상**
- 사용 함수: `statsmodels.tsa.stattools.kpss(regression='c', nlags='auto')`

### 4.3 병행 판정 기준

| ADF 결과 | KPSS 결과 | 최종 판정  | 비고               |
| -------- | --------- | ---------- | ------------------ |
| 정상     | 정상      | **정상**   | 일치               |
| 비정상   | 비정상    | **비정상** | 일치               |
| 정상     | 비정상    | **비정상** | 상충 → 보수적 처리 |
| 비정상   | 정상      | **비정상** | 상충 → 보수적 처리 |

보수적 원칙: 둘 중 하나라도 비정상이면 비정상으로 판정한다. 정상을 비정상으로 잘못 판단하면 효율성만 약간 떨어지지만, 비정상을 정상으로 잘못 판단하면 공적분 검정과 모형 추정 자체가 무효가 될 수 있기 때문이다.

### 4.4 KPSS regression='c' 선택 근거

KPSS 검정에는 `regression='c'`(상수항만)와 `regression='ct'`(상수항+추세) 두 가지 설정이 있다. `'c'`는 "평균 주위의 정상성"을, `'ct'`는 "추세 주위의 정상성"을 검정한다.

**'c' 선택 이유**:

1. **가격 시계열의 확률적 추세 특성**: CPI·PPI 등 가격 지수가 우상향하는 원인이 확정적 추세(매년 일정 비율 상승)가 아닌 확률적 추세(단위근, 충격 누적)에 기인한다는 것이 시계열 경제학의 표준 견해이다. 확률적 추세를 가진 시계열에 `'ct'`를 적용하면 불필요한 추세 파라미터를 추정하느라 자유도를 낭비하여 검정력이 저하된다.

2. **공적분 분석 프레임워크와의 일관성**: `'ct'`를 적용할 경우 일부 시계열이 I(0)으로 판정되어, 구간 내 쌍의 적분 차수가 불일치(I(0) vs I(1))하게 된다. 이 경우 Johansen 공적분 검정의 이론적 전제("동일 적분 차수 시계열 간 장기 균형")가 깨져 분석이 복잡해진다.

3. **실증 확인**: 대표 시계열 7개에서 `'c'`와 `'ct'` 결과를 비교한 결과, 5개는 판정이 동일하고 2건(쇠고기 PPI, 오렌지 CPI)만 상이하였다. 상이한 2건은 `'ct'`에서 p값이 5% 기준을 넘어 정상으로 판정되는 경우로, `'ct'` 적용 시 해당 품목의 구간 B에서 (import_price_usd = I(1), ppi = I(0)) 불일치가 발생한다.

| 시계열        | KPSS 'c' p값 | 판정   | KPSS 'ct' p값 | 판정     | 차이     |
| ------------- | ------------ | ------ | ------------- | -------- | -------- |
| 밀 PPI        | 0.01         | 비정상 | 0.01          | 비정상   | 동일     |
| 밀 CPI        | 0.01         | 비정상 | 0.01          | 비정상   | 동일     |
| 밀 국제가     | 0.01         | 비정상 | 0.03          | 비정상   | 동일     |
| 쇠고기 PPI    | 0.01         | 비정상 | 0.09          | **정상** | **상이** |
| 오렌지 CPI    | 0.01         | 비정상 | 0.09          | **정상** | **상이** |
| 커피 PPI      | 0.01         | 비정상 | 0.02          | 비정상   | 동일     |
| 오렌지 국제가 | 0.01         | 비정상 | 0.01          | 비정상   | 동일     |

결론: KPSS의 regression 설정에 따라 일부 시계열의 판정이 달라질 수 있으나, 가격 시계열의 확률적 추세 특성과 공적분 기반 분석 프레임워크의 일관성을 고려하여 `regression='c'`를 전 시계열에 통일 적용하였다.

### 4.5 처리 흐름

```
계절 조정 시계열 (수준, level)
    │
    ├─ ADF + KPSS 병행 검정
    │
    ├─ 둘 다 정상 → I(0), 수준 그대로 사용
    │
    ├─ 비정상 (일치 또는 상충)
    │     │
    │     ├─ 1차 차분 (X_t - X_{t-1})
    │     │
    │     ├─ ADF + KPSS 재검정
    │     │
    │     ├─ 정상 → I(1)
    │     └─ 여전히 비정상 → I(2) ⚠️
    │
    ▼
적분 차수 확정 → integration_orders.json 저장
```

### 4.6 검정 결과

총 43개 시계열 검정 결과:

| 적분 차수 | 개수 | 비율  | 설명                           |
| --------- | ---- | ----- | ------------------------------ |
| I(0)      | 0개  | 0%    | 수준에서 정상인 시계열 없음    |
| I(1)      | 41개 | 95.3% | 1차 차분 후 정상 — 정상적 결과 |
| I(2)      | 2개  | 4.7%  | 1차 차분 후에도 비정상 ⚠️      |

ADF-KPSS 상충: 4건 (쇠고기 PPI, 바나나 PPI, 오렌지 CPI, 오렌지 intl_price_krw) → 보수적으로 비정상 처리 후 차분하여 전부 I(1) 확정.

### 4.7 I(2) 시계열 상세

| 품목 | 컬럼           | 수준 ADF p | 수준 KPSS p | 차분 ADF p | 차분 KPSS p | 원인 추정                                       |
| ---- | -------------- | ---------- | ----------- | ---------- | ----------- | ----------------------------------------------- |
| 커피 | intl_price_krw | 0.2608     | 0.0100      | 0.3022     | 0.1000      | 2024~2026년 커피 국제가 지속 급등 (브라질 가뭄) |
| 땅콩 | ppi            | 0.9988     | 0.0100      | 0.0000     | 0.0243      | ADF 정상이나 KPSS 비정상 → 보수적 I(2) 처리     |

Phase 3 대응 방침:

- 커피 intl_price_krw는 차분 후 ADF p=0.302로 명확히 비정상. 2024~2026년 커피 국제가 급등이 1차 차분으로도 제거되지 않는 강한 추세를 형성한 것으로 추정
- 땅콩 ppi는 차분 후 ADF p=0.000(정상)이나 KPSS p=0.024(비정상)으로 상충. 보수적 원칙에 따라 I(2) 처리
- 두 시계열 모두 해당 구간에서 I(1)로 간주하고 공적분 검정을 진행하되, 결과에 주의 플래그를 부착한다
- 논문에서 연구의 한계로 명시한다

**참고 — 이전 데이터(2024-12 기준)와의 차이**: 이전에는 땅콩 wholesale_price(관측치 85개, ADF 검정력 부족)와 오렌지 intl_price_krw(2024년 급등 추세 잔존)가 I(2)였으나, 14개월 데이터 확장 후 두 건 모두 I(1)로 해소되었다. 대신 커피 intl_price_krw와 땅콩 ppi가 새로운 I(2)로 등장하여, I(2) 판정이 데이터 기간에 민감하다는 점이 확인되었다.

---

## 5. 산출물 구조

### 5.1 Phase 1 산출물

```
data/processed/phase1/
├── seasonal_adjusted/              ← 원본 + 계절 조정 수준 데이터
│   ├── wheat_sa.csv
│   ├── maize_sa.csv
│   └── ...                         (10개 파일)
│
├── changes/                        ← 전월 대비 변화율 (%) — Phase 2~7 주 입력
│   ├── wheat_changes.csv
│   ├── maize_changes.csv
│   └── ...                         (10개 파일)
│
├── stl_components/                 ← STL 분해 3성분 (trend, seasonal, resid)
│   ├── wheat_stl.csv
│   └── ...                         (10개 파일)
│
├── robustness/                     ← 계절 더미 방식 (Phase 8 로버스트니스용)
│   ├── wheat_dummy_sa.csv
│   ├── wheat_dummy_changes.csv
│   └── ...                         (20개 파일)
│
└── phase1_summary.csv              ← 43개 시계열 요약 통계
```

### 5.2 Phase 2 산출물

```
data/processed/phase2/
├── stationarity_results.csv        ← ADF+KPSS 전체 검정 결과 테이블
└── integration_orders.json         ← 품목·컬럼별 적분 차수 (Phase 3 입력)
```

---

## 6. CSV 컬럼 설명

### 6.1 `easonal_adjusted/{cid}_sa.csv`

| 컬럼         | 설명               | 용도                              |
| ------------ | ------------------ | --------------------------------- |
| date         | 월 기준일 (인덱스) | —                                 |
| commodity_id | 품목 식별자        | —                                 |
| {col}        | 원본 수준값        | 비교 참조용                       |
| `{col}_sa`   | 계절 조정 수준값   | Phase 3 Johansen 검정 입력 (VECM) |

3구간 품목: cpi, import_price_usd, intl_price_krw, ppi (4쌍)
4구간 품목: 위 4개 + wholesale_price (5쌍)

### 6.2 `changes/{cid}_changes.csv`

| 컬럼               | 설명                              | 출처                            |
| ------------------ | --------------------------------- | ------------------------------- |
| commodity_id       | 품목 식별자                       | —                               |
| `{col}_pct`        | 계절 조정 후 전월 대비 변화율 (%) | STL 적용 후 산출                |
| exchange_rate_pct  | 환율 변화율 (%)                   | 원본에서 직접 산출 (STL 미적용) |
| intl_price_usd_pct | 달러 국제가 변화율 (%)            | 원본에서 직접 산출 (STL 미적용) |

첫 행은 NaN. exchange_rate_pct와 intl_price_usd_pct는 Phase 7-ML의 외생 피처로 사용된다.

### 6.3 stationarity_results.csv

| 컬럼                               | 설명                                              |
| ---------------------------------- | ------------------------------------------------- |
| commodity_id, column               | 품목 및 가격 컬럼                                 |
| n_obs                              | 관측치 수                                         |
| level_adf_stat, level_adf_pvalue   | 수준 ADF 검정 통계량 및 p값                       |
| level_kpss_stat, level_kpss_pvalue | 수준 KPSS 검정 통계량 및 p값                      |
| level_judgment                     | 수준 검정 최종 판정 (stationary / non-stationary) |
| level_conflict_note                | ADF-KPSS 일치/상충 여부                           |
| diff_adf_stat, diff_adf_pvalue     | 차분 ADF 결과 (비정상 시에만)                     |
| diff_kpss_stat, diff_kpss_pvalue   | 차분 KPSS 결과 (비정상 시에만)                    |
| diff_judgment                      | 차분 검정 최종 판정                               |
| integration_order                  | 적분 차수 (0, 1, 또는 2)                          |

### 6.4 integration_orders.json

```json
{
  "wheat": {
    "cpi": 1,
    "import_price_usd": 1,
    "intl_price_krw": 1,
    "ppi": 1
  },
  "coffee": {
    "cpi": 1,
    "import_price_usd": 1,
    "intl_price_krw": 2,
    "ppi": 1
  },
  "groundnuts": {
    "cpi": 1,
    "import_price_usd": 1,
    "intl_price_krw": 1,
    "ppi": 2,
    "wholesale_price": 1
  }
}
```

Phase 3에서 이 파일을 읽어 구간별 두 변수의 적분 차수가 동일한지 확인하고, 공적분 검정 대상을 자동 판별한다.

---

## 7. 데이터 리니지

Phase 0~2의 데이터 변환 단계를 정리한다:

```
[원시 데이터]  raw levels ($/톤, 원/톤, 지수, 원/kg)
    │
    ▼  Phase 0: 수집·정제·병합
[merged CSV]  monthly levels, 결측 보간 완료
    │
    ▼  Phase 1: STL 분해
[_sa]  계절 조정 수준 데이터 = raw - seasonal
    │
    ├──▶  Phase 3 (Johansen 공적분 검정): 수준 데이터 입력
    │
    ▼  Phase 1: 변화율 산출
[_pct]  전월 대비 변화율 (%) = pct_change × 100
    │
    ├──▶  Phase 2 (정상성 검정): _sa 수준 데이터 검정
    ├──▶  Phase 4 (VAR 추정): 변화율 데이터 입력
    ├──▶  Phase 7 (패턴 1): 방향 비교 (부호)
    └──▶  Phase 7-ML: 상류·하류 변화율 피처
```

---

## 8. 다음 단계

Phase 2 완료 후 **Phase 3 (Johansen 공적분 검정)**으로 진행:

- integration_orders.json을 읽어 구간별 공적분 검정 대상 판별
- I(1) 쌍에 대해 Johansen Trace·Max-Eigen 통계량 검정
- 공적분 있음 → VECM 경로, 공적분 없음 → VAR 경로 분기
- I(2) 시계열 포함 구간은 주의 플래그 부착 후 진행
