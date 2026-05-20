# Phase 0 — 데이터 수집 및 전처리

> **작성일**: 2026-04-10  
> **목적**: Phase 0에서 수행한 데이터 수집·전처리 파이프라인의 전체 구조, 코드 역할, 실행 방법을 정리

---

## 1. 개요

Phase 0은 10개 품목의 가격 전달 분석에 필요한 원시 데이터를 6개 소스에서 수집하고, 분석 가능한 형태로 전처리하는 단계이다.

### 1.1 분석 대상 품목 (10개)

| #   | 품목   | commodity_id | 도매가 | 분석 경로     |
| --- | ------ | ------------ | ------ | ------------- |
| 1   | 밀     | wheat        | ✖      | A → B → D′    |
| 2   | 옥수수 | maize        | ✖      | A → B → D′    |
| 3   | 대두   | soybean      | ✖      | A → B → D′    |
| 4   | 팜유   | palmoil      | ✖      | A → B → D′    |
| 5   | 설탕   | sugar        | ✖      | A → B → D′    |
| 6   | 커피   | coffee       | ✖      | A → B → D′    |
| 7   | 쇠고기 | beef         | ✖      | A → B → D′    |
| 8   | 땅콩   | groundnuts   | ✔      | A → B → C → D |
| 9   | 바나나 | banana       | ✔      | A → B → C → D |
| 10  | 오렌지 | orange       | ✔      | A → B → C → D |

### 1.2 분석 구간

| 구간 | 상류 → 하류                  | 적용 품목            |
| ---- | ---------------------------- | -------------------- |
| A    | 국제가(원화 환산) → 수입단가 | 전체 10개            |
| B    | 수입단가 → PPI               | 전체 10개            |
| C    | PPI → 도매가                 | 땅콩, 바나나, 오렌지 |
| D    | 도매가 → CPI                 | 땅콩, 바나나, 오렌지 |
| D′   | PPI → CPI                    | 나머지 7개           |

---

## 2. 데이터 소스

| #   | 소스                  | 수집 방법                  | 수집기 코드                | 저장 위치                 |
| --- | --------------------- | -------------------------- | -------------------------- | ------------------------- |
| 1   | World Bank Pink Sheet | Excel 다운로드 + 파싱      | `collect_worldbank.py`     | `data/raw/worldbank/`     |
| 2   | FAO FFPI              | CSV 다운로드 + 파싱        | `parse_fao.py`             | `data/raw/fao/`           |
| 3   | 관세청 수입단가       | 수동 Excel 다운로드 + 파싱 | `parse_customs.py`         | `data/raw/customs/`       |
| 4   | 한국수출입은행 환율   | API 호출                   | `collect_exchange_rate.py` | `data/raw/exchange_rate/` |
| 5   | ECOS PPI/CPI          | API 호출                   | `collect_ecos.py`          | `data/raw/ecos/`          |
| 6   | KAMIS 도매가          | API 호출                   | `collect_kamis.py`         | `data/raw/kamis/`         |

---

## 3. 프로젝트 구조

```
price-transmission/
├── config/
│   └── commodity_mapping.json    ← 품목 매핑 테이블 (v3.1)
│
├── src/
│   ├── collectors/               ← 데이터 수집기
│   │   ├── collect_ecos.py           ECOS PPI/CPI 수집
│   │   ├── collect_exchange_rate.py  환율 수집 (월 5회, 분할 실행)
│   │   ├── collect_worldbank.py      World Bank 국제가 수집
│   │   ├── collect_kamis.py          KAMIS 도매가 수집 (monthlySalesList)
│   │   ├── parse_customs.py          관세청 수입단가 Excel 파서
│   │   ├── parse_fao.py              FAO FFPI CSV 파서
│   │   └── collect_all.py            전체 수집 실행기
│   │
│   └── preprocessing/            ← 전처리 파이프라인
│       ├── step1_convert_to_krw.py   국제가 원화 환산
│       ├── step2_common_period.py    공통 분석 기간 확정
│       ├── step3_missing_values.py   결측치 진단 + 보간
│       ├── step4_merge_datasets.py   품목별 통합 데이터셋 생성
│       ├── step5_product_config.py   PRODUCT_CONFIG 생성
│       └── run_phase0.py             Step 1~5 통합 실행
│
├── tests/                        ← API 검증 및 탐색 도구
│   ├── verify_apis_and_find_codes.py   ECOS/환율 API 키 검증
│   ├── find_all_10_items_codes.py      10개 품목 PPI/CPI 코드 조회
│   ├── find_ecos_ppi_stat_codes.py     PPI 통계표코드 전체 목록
│   ├── explore_ecos_ppi_tables.py      PPI 3개 통계표 비교
│   ├── explore_kamis_items.py          KAMIS 76개 품목 전수 조사
│   ├── check_kamis_items.py            KAMIS 부류별 품목 조회
│   ├── debug_ xxxxx.py                 KAMIS API 체크 용 파일
│   ├── test_kamis_monthly.py           monthlySalesList API 테스트
│   └── test_kamis_captions.py          KAMIS caption 확인
│
├── data/
│   ├── raw/                      ← 원시 데이터 (수집기 출력)
│   │   ├── worldbank/
│   │   ├── fao/
│   │   ├── customs/
│   │   ├── exchange_rate/
│   │   ├── ecos/
│   │   └── kamis/
│   │
│   ├── processed/                ← 전처리 출력
│   │   ├── worldbank_prices_krw.csv      원화 환산 국제가
│   │   ├── common_periods.csv            공통 분석 기간
│   │   ├── missing_value_report.csv      결측치 리포트
│   │   ├── product_config.json           품목별 분석 설정
│   │   └── merged/                       통합 데이터셋
│   │       ├── all_commodities.csv           전체 통합
│   │       ├── wheat.csv                     품목별 개별
│   │       ├── maize.csv
│   │       └── ...
│   │
│   └── output/                   ← 탐색 분석 출력
│
└── notebooks/
    └── explore_collected_data.py  ← 수집 데이터 탐색 분석
```

---

## 4. 실행 방법

### 4.1 데이터 수집

#### 원본 데이터는 압축 형태로 노션에서 공유 (data-raw.zip)

```bash
# 1. ECOS PPI/CPI (자동, ~1분)
python src/collectors/collect_ecos.py

# 2. 환율 — 일일 1000회 제한으로 분할 실행 필요
python src/collectors/collect_exchange_rate.py --start 2000 --end-year 2012
# (30분~1일 대기)
python src/collectors/collect_exchange_rate.py --start 2013

# 3. World Bank 국제가 (자동, ~10초)
python src/collectors/collect_worldbank.py

# 4. 관세청 수입단가 (수동 다운로드 → 파서 실행)
#    관세청에서 HS코드 11개 Excel 다운로드 후:
python src/collectors/parse_customs.py

# 5. KAMIS 도매가 (자동, ~2분)
python src/collectors/collect_kamis.py

# 6. FAO FFPI (수동 다운로드 → 파서 실행)
#    FAO 사이트에서 CSV 다운로드 후:
python src/collectors/parse_fao.py
```

### 4.2 전처리 (Step 1~5 통합 실행)

```bash
python src/preprocessing/run_phase0.py
```

또는 단계별 개별 실행:

```bash
python src/preprocessing/step1_convert_to_krw.py    # 국제가 원화 환산
python src/preprocessing/step2_common_period.py      # 공통 분석 기간
python src/preprocessing/step3_missing_values.py     # 결측치 진단
python src/preprocessing/step4_merge_datasets.py     # 통합 데이터셋
python src/preprocessing/step5_product_config.py     # PRODUCT_CONFIG
```

---

## 5. 수집 결과 현황

### 5.1 소스별 수집 현황

| 소스         | 품목 수            | 기간              | 비고                                 |
| ------------ | ------------------ | ----------------- | ------------------------------------ |
| ECOS PPI/CPI | 10개 (27개 시계열) | 2000-01 ~ 2026-03 | 커피 PPI 2019-12~, 땅콩 PPI 2017-12~ |
| World Bank   | 10개               | 2000-01 ~ 2026-02 | $/kg 품목 ×1000 변환 적용            |
| 관세청       | 10개 (HS 11개)     | 2000-01 ~ 2026-02 | 쇠고기 0201+0202 합산                |
| 환율         | 공통               | 2000-01 ~ 2026-04 | 월 5회(1,7,13,19,25일) 샘플링        |
| KAMIS        | 3개                | 1997-01 ~ 2026-04 | 쇠고기 제외 (축평원 데이터 미제공)   |
| FAO FFPI     | 6개 지수           | 2000-01 ~ 2026-03 | 교차검증용                           |

### 5.2 품목별 공통 분석 기간

| 품목                                                 | 기간              | 개월수 | 비고                        |
| ---------------------------------------------------- | ----------------- | ------ | --------------------------- |
| 밀, 옥수수, 대두, 팜유, 설탕, 쇠고기, 바나나, 오렌지 | 2000-01 ~ 2026-2 | 314    | —                           |
| 땅콩                                                 | 2017-12 ~ 2026-2 | 99     | PPI(견과가공품) 시작이 늦음 |
| 커피                                                 | 2019-12 ~ 2026-2 | 75     | PPI(원두커피) 시작이 늦음   |

### 5.3 결측치 현황

- 43개 시계열 중 41개: 결측 0건
- 땅콩 KAMIS: 결측 11.8% → 기준 완화(12%)하여 보간 적용
- 오렌지 KAMIS: 결측 3.3%, 연속 3개월 결측 1건 (2019-11~2020-01) → 선형 보간 적용

---

## 6. 통합 데이터셋 컬럼 설명

`data/processed/merged/` 내 CSV 파일 공통 스키마:

| 컬럼             | 설명                            | 단위       |
| ---------------- | ------------------------------- | ---------- |
| date             | 월 기준일                       | YYYY-MM-01 |
| commodity_id     | 품목 식별자                     | 문자열     |
| intl_price_usd   | 국제가 (달러)                   | $/톤       |
| intl_price_krw   | 국제가 (원화 환산)              | 원/톤      |
| exchange_rate    | 월평균 환율                     | 원/달러    |
| import_price_usd | 수입단가                        | $/톤       |
| ppi              | 생산자물가지수                  | 2020=100   |
| cpi              | 소비자물가지수                  | 2020=100   |
| wholesale_price  | KAMIS 도매가 (도매 경유 품목만) | 원/kg      |

---

## 7. PRODUCT_CONFIG

`data/processed/product_config.json`에 저장된 품목별 분석 설정:

```json
{
  "wheat": {
    "has_wholesale": false,
    "segments": ["A", "B", "D_prime"],
    "common_start": "2000-01",
    "common_end": "2026-02",
    "common_months": 314,
    "segment_pairs": {
      "A": ["intl_price_krw", "import_price_usd"],
      "B": ["import_price_usd", "ppi"],
      "D_prime": ["ppi", "cpi"]
    }
  }
}
```

Phase 1 이후의 파이프라인에서 이 설정을 읽어 품목별 분기를 수행한다.

---

## 8. 주의사항

### KAMIS API

- `dailyPriceByCategoryList`: 부류 필터가 작동하지 않음 (항상 식량작물 8개만 반환)
- `periodProductList`: 품목코드 필터 불안정, 과거 데이터 조회 불가
- `monthlySalesList`: 정상 작동. 품목코드가 다른 API와 다르므로 caption으로 검증 필수
- 쇠고기: 축평원 데이터 제외로 도매가 조회 불가

### 환율 수출입은행 API

- 일일 1,000회 호출 제한 → 월 5회 × 315개월 = 1,575회를 2일에 나눠 수집
- SSL 인증서 문제 → `verify=False` 필요
- 과도한 호출 시 IP 차단 (30분~1시간 후 해제)

### World Bank Pink Sheet

- 커피, 바나나, 오렌지, 쇠고기, 설탕은 $/kg 단위 → ×1000 변환하여 $/mt 통일
- 컬럼명이 정확히 일치해야 함 (Banana, US / Orange / Beef \*\* 등)

### ECOS PPI 통계표

- `404Y014`: 기본분류 (산업 대분류) — 제분, 사료, 유지 등
- `404Y016`: 품목별 (단일 품목) — 밀가루, 전분, 쇠고기 등
- 현재 대부분 404Y016 사용. 팜유·바나나·오렌지만 404Y014 사용 (개별 품목 코드 없음)

---

## 9. 다음 단계

Phase 0 완료 후 **Phase 1 (STL 계절 조정)**으로 진행:

- 각 시계열에 STL 분해 적용 → 계절 성분 제거
- 계절 조정 시계열에서 전월 대비 변화율 산출
- Phase 2~4(정상성 검정 → 공적분 검정 → VAR/VECM)의 입력 데이터 생성
