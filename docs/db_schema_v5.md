# DB 스키마 명세서

**과제명**: 계량경제학 모형과 머신러닝 기반 소비자 물가 분석 및 이상 탐지를 위한 모델 개발
**문서 유형**: PostgreSQL 16 DB 스키마 명세서 (v5)
**작성일**: 2026-04-20
**작성 기준** (최신 버전 자동 참조 — `abcd_vN.md` 규칙): `pipeline_output_spec_vN.md` / `web_plan_vN.md` / `doc1_technical_pipeline_vN.md` / `doc2_pattern_definitions_vN.md`
**변경 이력**:
- v1 → v2: 당시 design_review v1 검토 반영. 주요 변경: D-01(asymmetry_results.subperiod_id 제거), D-02(anomaly_results는 탐지 행만 저장 명시, confidence_grade NOT NULL 유지), D-03(anomaly_results에 zscore_warning 추가), D-05(anomaly_results에 pattern1_flag_type 추가), D-06(baselines에 warmup_end 추가), D-07(breakpoints JSON→DB 변환 규칙 명시), D-08(mv_anomaly_density_yearly 머티리얼라이즈드 뷰 추가), D-09(이벤트 오버레이 정책 명시), D-10(granger_results.segment_id FK 추가), D-11(월 기준일 검증 정책 명시), D-13(anomaly_results UNIQUE 제약 수정·pattern1_flag_type 추가), D-17(배치 롤백 정책 명시), D-18(Redis 캐시 무효화 방향성 기록), D-19(ml_projections 저장 범위 방침 기록), D-20(에러 envelope context 필드 추가 — API 명세 반영).
- v2 → v3: 당시 pipeline_output_spec v5 반영. 설계 원칙 2번 버전 참조 갱신. stationarity_results·cointegration_results 대응 명세 버전 갱신. model_params.lag_criterion 컬럼 주석 재정의(Phase 4 자체 시차 선택 없음 — Phase 3 결정값 기록용). 푸터 버전 갱신.
- v3 → v4: 당시 pipeline_output_spec v6 업데이트.
- v4 → v5 (2026-05-02): 본문 정정. `reference_audit_report v1` §4 규칙에 따라 외부 참조 표기를 `abcd_vN.md`로 일괄 전환. 헤더 `작성 기준`의 구버전 참조(당시 doc1 v9) 정정. 본 문서는 이제 `docs/docs_manifest.md`의 버전 해석기에 의해 자동 최신 참조되며, 파일명·본문·푸터는 `_v5`로 정합.

---

## 개요

### 목적

파이프라인(Phase 0~9) 산출물을 PostgreSQL 16에 적재하고, FastAPI 백엔드를 통해 프론트엔드에 제공하기 위한 테이블 구조를 정의한다.

### 설계 원칙

1. **읽기 최적화 우선** — 웹 서비스는 배치 적재 후 읽기 전용으로 동작한다. 쓰기 성능보다 쿼리 속도를 우선한다.
2. **파이프라인 출력과 1:1 대응** — 각 테이블은 `pipeline_output_spec_vN`의 출력 파일 단위에 대응하며, 컬럼 이름은 가능한 한 동일하게 유지한다.
3. **웹 서비스 API 단위 분리** — `web_plan_vN` §12의 API 엔드포인트 단위로 테이블을 분리하여 조인 비용을 최소화한다.
4. **v2 과적재 원칙** — 파이프라인 출력이 미확정인 Phase 3~7 산출물은 넉넉하게 컬럼을 정의한다. 검수 후 불필요한 컬럼은 제거한다.
5. **탐지 이벤트만 저장 (D-02)** — `anomaly_results` 테이블은 이상 탐지된 행만 저장한다. `confidence_grade IS NOT NULL`인 행만 적재한다. 정상 월은 저장하지 않는다.
6. **월 기준일 검증 (D-11)** — `period DATE` 컬럼을 갖는 모든 테이블에서 `period`는 반드시 **월초(`YYYY-MM-01`)** 값으로 고정한다. 적재 시 `period.day == 1` 검증을 수행하며, 월말 기준 저장을 방지한다.
7. **배치 롤백 정책 (D-17)** — 각 Phase 적재는 단일 트랜잭션으로 묶는다. 실패 시 해당 Phase 전체를 롤백하고 `pipeline_runs.status='failed'`로 기록한다. 다음 재실행은 마지막 `completed` 상태 Phase부터 재시작한다.

### DB 구성

| 항목 | 값 |
|---|---|
| RDBMS | PostgreSQL 16 |
| 캐시 | Redis (시각화 데이터 캐싱 — 스키마 범위 외) |
| ORM | SQLAlchemy 2.0 (비동기) |
| 스키마 | `public` 단일 스키마 |

### 테이블 목록

| 그룹 | 테이블명 | 역할 |
|---|---|---|
| 참조 | `commodities` | 품목 메타 정보 |
| 참조 | `segments` | 분석 구간 정의 |
| 참조 | `external_events` | 외부 충격 이벤트 목록 |
| 원시 가격 | `raw_prices` | 원시 시계열 (원본값 + 2020=100 지수) |
| 계량 | `stationarity_results` | Phase 2 ADF+KPSS 검정 결과 |
| 계량 | `cointegration_results` | Phase 3 Johansen 공적분 검정 결과 |
| 계량 | `model_params` | Phase 4 VAR/VECM 추정 파라미터 |
| 계량 | `irf_data` | Phase 4 IRF 곡선 데이터 |
| 계량 | `baselines` | Phase 4 기준선 (정상 전달 시차·전이탄력성·warmup_end) |
| 계량 | `granger_results` | Phase 5 Granger 인과 검정 결과 |
| 계량 | `breakpoints` | Phase 6 구조 변화 시점 |
| 계량 | `subperiods` | Phase 6 하위 기간 분할 정보 |
| 탐지 | `stat_timeseries` | Phase 7 지표별 전체 시계열 (전이율·Z-score·ECT 등) |
| 탐지 | `anomaly_results` | Phase 7+7-ML 이상 탐지 결과 + 신뢰도 등급 (탐지 이벤트만) |
| 탐지 | `asymmetry_results` | Phase 7 패턴 2 비대칭 검정 결과 |
| ML | `ml_scores` | Phase 7-ML 모델별 이상 점수 |
| ML | `ml_projections` | Phase 7-ML ML 결과맵 2D 투영 데이터 |
| 배치 | `pipeline_runs` | 월별 배치 실행 이력 |
| 배치 | `data_freshness` | 데이터 기준 시점 및 다음 갱신 예정일 |
| 집계 뷰 | `mv_anomaly_density_yearly` | 연도별 이상 밀도 머티리얼라이즈드 뷰 (미니맵용) |

---

## 참조 테이블

### `commodities` — 품목 메타 정보

```sql
CREATE TABLE commodities (
    id              SERIAL PRIMARY KEY,
    commodity_id    VARCHAR(20)  NOT NULL UNIQUE,  -- 'wheat', 'maize', ...
    name_kr         VARCHAR(50)  NOT NULL,           -- '밀', '옥수수', ...
    name_en         VARCHAR(50)  NOT NULL,
    cluster         VARCHAR(30),                     -- 'grain', 'oil_sugar', 'tropical', 'livestock', 'independent'
    has_wholesale   BOOLEAN      NOT NULL DEFAULT FALSE,
    route_type      VARCHAR(10)  NOT NULL,           -- '3seg' | '4seg'
    analysis_start  DATE,                            -- 품목별 분석 시작 시점 (Phase 0 완료 후 확정)
    analysis_end    DATE,                            -- 현재 데이터 기준 종료 시점
    pinksheet_var   VARCHAR(100),                    -- Pink Sheet 변수명 (예: 'Wheat, US HRW')
    hs_code         VARCHAR(20),                     -- HS 코드 (예: '1001')
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

**초기 데이터 (10개 행)**

| commodity_id | name_kr | cluster | has_wholesale | route_type |
|---|---|---|---|---|
| wheat | 밀 | grain | false | 3seg |
| maize | 옥수수 | grain | false | 3seg |
| soybean | 대두 | grain | false | 3seg |
| palm_oil | 팜유 | oil_sugar | false | 3seg |
| sugar | 설탕 | oil_sugar | false | 3seg |
| coffee | 커피 | tropical | false | 3seg |
| beef | 소고기 | livestock | false | 3seg |
| groundnuts | 땅콩 | independent | true | 4seg |
| banana | 바나나 | tropical | true | 4seg |
| orange | 오렌지 | independent | true | 4seg |

---

### `segments` — 분석 구간 정의

```sql
CREATE TABLE segments (
    id              SERIAL PRIMARY KEY,
    segment_id      VARCHAR(10)  NOT NULL UNIQUE,  -- 'A', 'B', 'C', 'D', 'D_prime'
    label_kr        VARCHAR(50)  NOT NULL,           -- '구간 A (국제가→수입단가)'
    upstream_col    VARCHAR(50)  NOT NULL,           -- 'intl_price_krw'
    downstream_col  VARCHAR(50)  NOT NULL,           -- 'import_price_usd'
    upstream_label  VARCHAR(50)  NOT NULL,           -- '국제가 (원화 환산)'
    downstream_label VARCHAR(50) NOT NULL,           -- '수입단가'
    applies_to      VARCHAR(10)  NOT NULL,           -- 'all' | '3seg' | '4seg'
    pattern1        BOOLEAN      NOT NULL DEFAULT TRUE,
    pattern2        BOOLEAN      NOT NULL DEFAULT FALSE,
    pattern3        BOOLEAN      NOT NULL DEFAULT FALSE,
    ml_applied      BOOLEAN      NOT NULL DEFAULT FALSE
);
```

**초기 데이터 (5개 행)**

| segment_id | applies_to | pattern1 | pattern2 | pattern3 | ml_applied |
|---|---|:---:|:---:|:---:|:---:|
| A | all | ✔ | ✔ | — | ✔ |
| B | all | ✔ | ✔ | ✔ | ✔ |
| C | 4seg | ✔ | — | — | — |
| D | 4seg | ✔ | — | — | — |
| D_prime | 3seg | ✔ | — | — | — |

---

### `external_events` — 외부 충격 이벤트

이벤트 배경 음영 정책 (D-09): 이벤트 오버레이는 프론트엔드가 `/events` 엔드포인트를 **별도 조회**한 후 클라이언트에서 시계열에 오버레이하는 방식을 기본으로 한다. 시계열 엔드포인트 응답에 이벤트 데이터를 포함하지 않는다.

```sql
CREATE TABLE external_events (
    id          SERIAL PRIMARY KEY,
    event_key   VARCHAR(50)  NOT NULL UNIQUE,  -- 'financial_crisis_2008', ...
    label_kr    VARCHAR(100) NOT NULL,
    start_date  DATE         NOT NULL,
    end_date    DATE         NOT NULL,
    color_hex   VARCHAR(10)  NOT NULL,          -- 배경 음영 색상 (HEX)
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

**초기 데이터 (5개 행, web_plan_vN §3.4 기준)**

| event_key | label_kr | start_date | end_date | color_hex |
|---|---|---|---|---|
| financial_crisis_2008 | 2008 금융위기 | 2008-07-01 | 2009-03-31 | #F97316 |
| covid19_2020 | 2020 코로나19 | 2020-02-01 | 2021-06-30 | #22C55E |
| brazil_frost_2021 | 2021~22 브라질 서리 | 2021-07-01 | 2022-03-31 | #38BDF8 |
| ukraine_2022 | 2022 우크라이나 사태 | 2022-02-01 | 2022-10-31 | #EF4444 |
| indonesia_palmoil_2022 | 2022 인도네시아 팜유 수출 규제 | 2022-04-01 | 2022-05-31 | #FB923C |

---

## 원시 가격 테이블

### `raw_prices` — 원시 시계열

원시 시계열 뷰(web_plan_vN §4.3)에서 사용. Phase 0 `merged/{cid}.csv` 기준으로 적재하며, Y축 통일을 위한 2020=100 지수 환산값을 함께 저장한다.

```sql
CREATE TABLE raw_prices (
    id                      SERIAL PRIMARY KEY,
    commodity_id            VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    period                  DATE         NOT NULL,  -- 월 기준일 (YYYY-MM-01)

    -- 원본값
    intl_price_usd          NUMERIC(14,4),   -- 국제가 달러 ($/톤)
    intl_price_krw          NUMERIC(14,4),   -- 국제가 원화 환산
    import_price_usd        NUMERIC(14,4),   -- 수입단가 ($/톤)
    exchange_rate           NUMERIC(10,4),   -- 월평균 원/달러 환율
    ppi                     NUMERIC(12,4),   -- 생산자물가지수
    cpi                     NUMERIC(12,4),   -- 소비자물가지수
    wholesale_price         NUMERIC(14,4),   -- KAMIS 도매가 (4구간 품목만, 나머지 NULL)

    -- 2020=100 지수 환산값 (원시 시계열 뷰 Y축 통일용)
    intl_price_krw_idx      NUMERIC(10,4),   -- 국제가 원화 2020=100 지수
    import_price_idx        NUMERIC(10,4),   -- 수입단가 2020=100 지수
    ppi_idx                 NUMERIC(10,4),   -- PPI 2020=100 지수
    cpi_idx                 NUMERIC(10,4),   -- CPI 2020=100 지수
    wholesale_price_idx     NUMERIC(10,4),   -- 도매가 2020=100 지수 (NULL 가능)

    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, period)
);

CREATE INDEX idx_raw_prices_commodity_period ON raw_prices (commodity_id, period);
```

---

## 계량경제학 테이블

### `stationarity_results` — Phase 2 정상성 검정 결과

`pipeline_output_spec_vN`의 `phase2/stationarity_results.csv`에 대응.

```sql
CREATE TABLE stationarity_results (
    id                      SERIAL PRIMARY KEY,
    commodity_id            VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    price_col               VARCHAR(50)  NOT NULL,  -- 'intl_price_krw', 'ppi', ...
    n_obs                   INTEGER      NOT NULL,

    -- 수준(level) 검정
    level_adf_stat          NUMERIC(10,4),
    level_adf_pvalue        NUMERIC(8,4),
    level_adf_lags          SMALLINT,
    level_adf_stationary    BOOLEAN,
    level_kpss_stat         NUMERIC(10,4),
    level_kpss_pvalue       NUMERIC(8,4),
    level_kpss_stationary   BOOLEAN,
    level_judgment          VARCHAR(20),             -- 'stationary' | 'non-stationary'
    level_conflict_note     VARCHAR(50),             -- '일치 (둘 다 정상)' | '상충 → 비정상 (보수적)' 등

    -- 차분(diff) 검정 (비정상 시에만)
    diff_adf_stat           NUMERIC(10,4),
    diff_adf_pvalue         NUMERIC(8,4),
    diff_kpss_stat          NUMERIC(10,4),
    diff_kpss_pvalue        NUMERIC(8,4),
    diff_judgment           VARCHAR(20),

    -- 최종
    integration_order       SMALLINT     NOT NULL,   -- 0, 1, 2
    i2_flag                 BOOLEAN      NOT NULL DEFAULT FALSE,

    pipeline_run_id         INTEGER      REFERENCES pipeline_runs(id),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, price_col)
);
```

---

### `cointegration_results` — Phase 3 Johansen 공적분 검정 결과

`pipeline_output_6`의 `phase3/cointegration_results.csv`에 대응.

```sql
CREATE TABLE cointegration_results (
    id                              SERIAL PRIMARY KEY,
    commodity_id                    VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id                      VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    upstream_col                    VARCHAR(50)  NOT NULL,
    downstream_col                  VARCHAR(50)  NOT NULL,

    upstream_integration_order      SMALLINT,
    downstream_integration_order    SMALLINT,
    integration_order_match         BOOLEAN,
    coint_tested                    BOOLEAN      NOT NULL DEFAULT FALSE,  -- I(1) 쌍만 True

    -- Johansen 검정 결과
    trace_stat                      NUMERIC(10,4),
    trace_pvalue                    NUMERIC(8,4),
    maxeig_stat                     NUMERIC(10,4),
    maxeig_pvalue                   NUMERIC(8,4),
    coint_rank                      SMALLINT,           -- 0 또는 1
    cointegrated                    BOOLEAN,
    i2_flag                         BOOLEAN      NOT NULL DEFAULT FALSE,

    -- Phase 4 모형 분기 결과
    model_type                      VARCHAR(10),        -- 'VAR' | 'VECM'

    -- Phase 5 Granger 결과 갱신 후 채워짐 (4구간 구간 C만)
    granger_direction               VARCHAR(30),        -- 'ppi_to_wholesale' | 'wholesale_to_ppi' | 'bidirectional' | 'none' | NULL

    pipeline_run_id                 INTEGER      REFERENCES pipeline_runs(id),
    created_at                      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id)
);
```

---

### `model_params` — Phase 4 모형 추정 파라미터

```sql
CREATE TABLE model_params (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    subperiod_id        INTEGER      REFERENCES subperiods(id),  -- NULL이면 전체 기간 모형

    model_type          VARCHAR(10)  NOT NULL,  -- 'VAR' | 'VECM'
    lag_selected        SMALLINT     NOT NULL,
    lag_criterion       VARCHAR(10)  NOT NULL DEFAULT 'AIC',  -- Phase 3에서 시차 선택 시 사용한 기준 기록용 ('AIC' | 'BIC'). Phase 4는 시차를 재선택하지 않으며 Phase 3 결정값을 전달받아 사용한다.
    n_obs               INTEGER      NOT NULL,
    estimation_start    DATE         NOT NULL,
    estimation_end      DATE         NOT NULL,
    cointegrated        BOOLEAN      NOT NULL,
    det_order           SMALLINT,               -- VECM det_order (0 고정)
    coint_rank          SMALLINT,               -- VECM 공적분 벡터 수

    -- 모형 적합도 지표
    aic                 NUMERIC(14,4),
    bic                 NUMERIC(14,4),
    log_likelihood      NUMERIC(14,4),

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, subperiod_id)
);
```

---

### `irf_data` — Phase 4 IRF 곡선 데이터

분석 수치 패널 §IRF 차트(web_plan_vN §6.5)에서 사용. 전체 기간 + 하위 기간별 IRF를 저장.

```sql
CREATE TABLE irf_data (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    subperiod_id        INTEGER      REFERENCES subperiods(id),  -- NULL이면 전체 기간

    horizon             SMALLINT     NOT NULL,   -- 충격 후 경과 개월 수 (0~24)
    irf_downstream      NUMERIC(12,6) NOT NULL,  -- 하류 가격 누적 반응값
    irf_lower_ci        NUMERIC(12,6),           -- 95% 신뢰구간 하한
    irf_upper_ci        NUMERIC(12,6),           -- 95% 신뢰구간 상한

    -- 피크 정보 (horizon=0 행에만 저장, 나머지 행은 NULL)
    irf_peak_horizon    SMALLINT,                -- IRF 피크 도달 시점 (개월)
    irf_peak_magnitude  NUMERIC(12,6),           -- IRF 피크 크기 (전이탄력성 기준값)

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, subperiod_id, horizon)
);

CREATE INDEX idx_irf_commodity_segment ON irf_data (commodity_id, segment_id, subperiod_id);
```

---

### `baselines` — Phase 4 기준선 파라미터

Phase 7 이상 탐지의 기준선. 분석 수치 패널에서 "정상 전달 시차 N개월", "전이탄력성 X" 표시에 사용.

`warmup_end`는 `estimation_start + 48개월`로 산출하여 저장한다 (D-06). API의 `segment_meta.{seg}.warmup_end`는 이 컬럼을 직접 반환한다.

API 노출 기준 (D-15): `segment_meta`에 반환되는 `normal_transmission_lag`·`transmission_elasticity`는 **전체 기간 기준선** (`subperiod_id IS NULL`) 값이다. 하위 기간별 기준선은 IRF 엔드포인트를 통해서만 노출한다.

```sql
CREATE TABLE baselines (
    id                          SERIAL PRIMARY KEY,
    commodity_id                VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id                  VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    subperiod_id                INTEGER      REFERENCES subperiods(id),  -- NULL이면 전체 기간 기준선

    normal_transmission_lag     SMALLINT     NOT NULL,  -- IRF 피크 시점 (개월) — 패턴 1 기준
    transmission_elasticity     NUMERIC(10,4) NOT NULL, -- IRF 피크 크기 — 패턴 2 참조값
    warmup_end                  DATE         NOT NULL,  -- 롤링 윈도우 축적 완료 시점 (estimation_start + 48개월)
    model_type                  VARCHAR(10)  NOT NULL,
    estimation_start            DATE         NOT NULL,
    estimation_end              DATE         NOT NULL,
    n_obs                       INTEGER      NOT NULL,

    pipeline_run_id             INTEGER      REFERENCES pipeline_runs(id),
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, subperiod_id)
);
```

---

### `granger_results` — Phase 5 Granger 인과 검정 결과

4구간 품목(groundnuts, banana, orange) 구간 C에만 존재.

```sql
CREATE TABLE granger_results (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL DEFAULT 'C'
                                     REFERENCES segments(segment_id),  -- FK 추가 (D-10)

    -- 방향별 검정 결과 (2행 또는 1행으로 저장)
    direction           VARCHAR(30)  NOT NULL,   -- 'ppi_to_wholesale' | 'wholesale_to_ppi'
    max_lag             SMALLINT     NOT NULL,
    f_stat              NUMERIC(10,4),
    pvalue              NUMERIC(8,4),
    significant         BOOLEAN      NOT NULL,

    -- 확정 방향 (commodity_id 단위로 동일한 값)
    confirmed_direction VARCHAR(30),             -- 'ppi_to_wholesale' | 'wholesale_to_ppi' | 'bidirectional' | 'none'

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, direction)
);
```

---

### `breakpoints` — Phase 6 구조 변화 시점

Chow Test 시점은 `2008-01`, `2020-01`, `2022-01` **고정 3개** (D-07). JSON `chow_test_points` 키에서 직접 매핑한다.

```sql
CREATE TABLE breakpoints (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),

    -- Bai-Perron 탐지 결과 (배열로 저장)
    -- 적재 규칙: pipeline JSON "YYYY-MM" → DATE "YYYY-MM-01"로 월초 승격
    bp_dates            DATE[],                  -- 탐지된 변화 시점 목록

    -- Chow Test 결과 (고정 3개 시점)
    chow_2008_f         NUMERIC(10,4),
    chow_2008_pvalue    NUMERIC(8,4),
    chow_2008_sig       BOOLEAN,
    chow_2020_f         NUMERIC(10,4),
    chow_2020_pvalue    NUMERIC(8,4),
    chow_2020_sig       BOOLEAN,
    chow_2022_f         NUMERIC(10,4),
    chow_2022_pvalue    NUMERIC(8,4),
    chow_2022_sig       BOOLEAN,

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id)
);
```

---

### `subperiods` — Phase 6 하위 기간 분할

```sql
CREATE TABLE subperiods (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    subperiod_index     SMALLINT     NOT NULL,   -- 1, 2, 3, ...
    -- 적재 규칙: pipeline JSON "YYYY-MM" → DATE "YYYY-MM-01"로 월초 승격
    period_start        DATE         NOT NULL,
    period_end          DATE         NOT NULL,
    n_obs               INTEGER      NOT NULL,
    merged_with_index   SMALLINT,                -- 60개 미달 시 병합 대상 subperiod_index (NULL이면 독립)

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, subperiod_index)
);
```

---

## 이상 탐지 테이블

### `stat_timeseries` — Phase 7 지표별 시계열

분석 수치 패널에서 지표 항목 클릭 시 표시되는 개별 인라인 그래프(web_plan_vN §6.2) 및 스트림 그래프의 전이율 곡선 데이터 소스.

```sql
CREATE TABLE stat_timeseries (
    id                      SERIAL PRIMARY KEY,
    commodity_id            VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id              VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    period                  DATE         NOT NULL,   -- 월 기준일 (YYYY-MM-01)

    -- 전이율 (스트림 그래프 Y축 직접값, 패턴 2 판정 기반)
    transmission_rate       NUMERIC(12,6),           -- 하류 변화율 ÷ 상류 변화율
    upstream_pct            NUMERIC(12,6),           -- 상류 가격 변화율 (%)
    downstream_pct          NUMERIC(12,6),           -- 하류 가격 변화율 (%)

    -- 롤링 Z-score + IQR (패턴 2, W=48 기본)
    rolling_mean            NUMERIC(12,6),
    rolling_std             NUMERIC(12,6),
    zscore                  NUMERIC(10,4),
    q1                      NUMERIC(12,6),
    q3                      NUMERIC(12,6),
    iqr                     NUMERIC(12,6),
    iqr_lower               NUMERIC(12,6),           -- Q1 - 1.5×IQR
    iqr_upper               NUMERIC(12,6),           -- Q3 + 1.5×IQR
    in_warmup_period        BOOLEAN      NOT NULL DEFAULT FALSE,

    -- 로버스트니스용 추가 롤링 (W=36, W=60)
    zscore_w36              NUMERIC(10,4),
    zscore_w60              NUMERIC(10,4),

    -- ECT 또는 로그 수준 스프레드 (패턴 3, Phase 7-ML 피처)
    ect_or_spread           NUMERIC(12,6),
    ect_type                VARCHAR(15),             -- 'ECT' | 'log_spread'

    -- 패턴 3 안정 구간 여부
    in_stable_period        BOOLEAN,                 -- 국제가 월 변동 ±3% 이내
    spread_n2               NUMERIC(12,6),
    spread_n3               NUMERIC(12,6),
    spread_n6               NUMERIC(12,6),

    -- 외생 피처 (Phase 7-ML 입력용)
    exchange_rate_pct       NUMERIC(12,6),
    intl_price_usd_pct      NUMERIC(12,6),

    pipeline_run_id         INTEGER      REFERENCES pipeline_runs(id),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, period)
);

CREATE INDEX idx_stat_ts_commodity_segment_period
    ON stat_timeseries (commodity_id, segment_id, period DESC);
```

`metric=breakpoints` 조회 시 `bp_dates`는 `breakpoints` 테이블에서 조회한다 (D-16 수정: `baselines.bp_dates`는 오기였으며 `breakpoints.bp_dates`가 정확한 출처다).

---

### `anomaly_results` — 이상 탐지 결과 + 신뢰도 등급

파이프라인의 최종 산출물. **탐지된 이벤트만 저장** (`confidence_grade IS NOT NULL` 행만 적재, D-02).

스트림 그래프 이상 노드, 분석 수치 패널 헤더, 이달의 이상 요약 배너, 툴팁 데이터 소스.

UNIQUE 제약은 `(commodity_id, segment_id, period)`로 설정한다 (D-13). 동일 월·구간에 복수 패턴이 탐지될 경우 **1개 행**으로 저장하고 `pattern_types` 배열에 전체 패턴을, `primary_pattern`에 대표 패턴(심각도 기준: pattern2 > pattern1 > pattern3)을 저장한다.

```sql
CREATE TABLE anomaly_results (
    id                      SERIAL PRIMARY KEY,
    commodity_id            VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id              VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    period                  DATE         NOT NULL,   -- 이상 탐지 월 (YYYY-MM-01)

    -- 패턴 (복수 패턴이 동일 월·구간에 발생할 수 있으므로 배열)
    pattern_types           VARCHAR(10)[] NOT NULL,  -- {'pattern1'}, {'pattern2'}, {'pattern1','pattern2'} 등
    primary_pattern         VARCHAR(10)  NOT NULL,   -- 대표 패턴 (복수일 때 가장 심각한 것)

    -- 패턴 1 세부
    direction_reversal      BOOLEAN      NOT NULL DEFAULT FALSE,
    lag_deviation           BOOLEAN      NOT NULL DEFAULT FALSE,
    pattern1_flag_type      VARCHAR(20),             -- 'direction_reversal' | 'lag_deviation' | 'both' (D-05)
    actual_lag              SMALLINT,                -- 실제 반응 시차 (개월)
    normal_lag              SMALLINT,                -- 기준선 정상 전달 시차

    -- 패턴 2 세부
    transmission_rate       NUMERIC(12,6),           -- 해당 월 전이율
    zscore_value            NUMERIC(10,4),
    zscore_warning          BOOLEAN      NOT NULL DEFAULT FALSE,  -- Z-score > 2.0 (D-03)
    zscore_alert            BOOLEAN      NOT NULL DEFAULT FALSE,  -- Z-score > 2.5
    iqr_outlier             BOOLEAN      NOT NULL DEFAULT FALSE,
    over_transmission       BOOLEAN      NOT NULL DEFAULT FALSE,
    under_transmission      BOOLEAN      NOT NULL DEFAULT FALSE,

    -- 패턴 3 세부
    spread_n3_value         NUMERIC(12,6),           -- N=3 기준 누적 스프레드 변화
    pattern3_n              SMALLINT,                -- 탐지된 N값 (2, 3, 또는 6)

    -- 통계 탐지 여부
    stat_detected           BOOLEAN      NOT NULL DEFAULT TRUE,

    -- ML 판정
    ml_detected             BOOLEAN      NOT NULL DEFAULT FALSE,
    ml_vote                 SMALLINT     NOT NULL DEFAULT 0,  -- 0~3
    if_anomaly              BOOLEAN,
    lof_anomaly             BOOLEAN,
    svm_anomaly             BOOLEAN,

    -- 신뢰도 등급 (신청서 기준 3단계, NOT NULL — 정상 행은 적재하지 않음)
    confidence_grade        VARCHAR(15)  NOT NULL,
    -- 'high'      : 통계 O + ML 동시 확인
    -- 'medium'    : 통계 O + ML 미탐지
    -- 'reference' : ML O + 통계 미탐지

    -- 하위 기간 정보
    subperiod_id            INTEGER      REFERENCES subperiods(id),

    -- 배너 및 NEW 배지
    is_new                  BOOLEAN      NOT NULL DEFAULT FALSE,  -- 이번 배치에서 신규 탐지

    pipeline_run_id         INTEGER      REFERENCES pipeline_runs(id),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- D-13: primary_pattern을 UNIQUE에서 제거하여 동월 복수 패턴을 1행으로 저장
    UNIQUE (commodity_id, segment_id, period)
);

-- 스트림 그래프 · 배너 조회 최적화
CREATE INDEX idx_anomaly_commodity_period ON anomaly_results (commodity_id, period DESC);
CREATE INDEX idx_anomaly_grade ON anomaly_results (confidence_grade, period DESC);
CREATE INDEX idx_anomaly_is_new ON anomaly_results (is_new) WHERE is_new = TRUE;
```

---

### `asymmetry_results` — Phase 7 패턴 2 비대칭 검정 결과

구간 A·B **전체 기간 단위만** 산출 (D-01 확정: 하위 기간별 비대칭 검정 미수행). `subperiod_id`는 항상 NULL로 저장된다.

```sql
CREATE TABLE asymmetry_results (
    id                      SERIAL PRIMARY KEY,
    commodity_id            VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id              VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    -- subperiod_id 컬럼 없음 (D-01: 전체 기간 단일 검정만 수행)

    model_type              VARCHAR(20)  NOT NULL,  -- 'TECM' | 'asymmetric_VAR'

    -- TECM 결과 (공적분 있는 구간)
    alpha_plus              NUMERIC(10,6),   -- α⁺: 상승 국면 조정 계수
    alpha_minus             NUMERIC(10,6),   -- α⁻: 하락 국면 조정 계수
    wald_stat               NUMERIC(10,4),   -- Wald 검정 통계량 (H₀: α⁺ = α⁻)
    wald_pvalue             NUMERIC(8,4),

    -- 비대칭 VAR 결과 (공적분 없는 구간)
    up_coef                 NUMERIC(10,6),   -- 상승기 전이 계수
    down_coef               NUMERIC(10,6),   -- 하락기 전이 계수

    -- 공통 판정
    asymmetry_significant   BOOLEAN      NOT NULL DEFAULT FALSE,
    rocket_feather_direction VARCHAR(20),    -- 'upward_stronger' | 'downward_stronger' | NULL

    pipeline_run_id         INTEGER      REFERENCES pipeline_runs(id),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id)
);
```

---

## ML 테이블

### `ml_scores` — Phase 7-ML 모델별 이상 점수

분석 수치 패널 ML 판정 섹션의 이상 점수 바 차트(web_plan_vN §6.3)에 사용.

```sql
CREATE TABLE ml_scores (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    period              DATE         NOT NULL,

    -- Isolation Forest
    if_score            NUMERIC(10,6),   -- 이상 점수 (낮을수록 이상)
    if_anomaly          BOOLEAN,
    if_percentile       NUMERIC(6,2),    -- 전체 분포 상 퍼센타일 위치

    -- LOF
    lof_score           NUMERIC(10,6),   -- LOF 이상 점수
    lof_anomaly         BOOLEAN,
    lof_percentile      NUMERIC(6,2),

    -- One-Class SVM
    svm_score           NUMERIC(10,6),   -- decision function 값 (음수이면 이상)
    svm_anomaly         BOOLEAN,
    svm_percentile      NUMERIC(6,2),

    -- 앙상블
    ml_vote             SMALLINT,        -- 0~3
    ml_detected         BOOLEAN,         -- 2개 이상 탐지 시 True

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, period)
);

CREATE INDEX idx_ml_scores_commodity_segment ON ml_scores (commodity_id, segment_id, period DESC);
```

---

### `ml_projections` — Phase 7-ML ML 결과맵 2D 투영 데이터

분석 수치 패널 ML 결과맵(web_plan_vN §6.3) 시각화에 사용. 투영 축(PCA 2D vs 직접 피처 2종)은 OI-15에 따라 S4 스프린트 내 확정.

저장 범위 방침 (D-19): OI-15 결정 후 `projection_method`를 단일로 확정하거나, "이상 탐지 월 ± 12개월" 범위만 저장하는 방식을 검토한다. 현재는 전 관측치 저장 구조로 설계하나, 배치 완료 후 실제 행 수를 확인하여 축소 여부를 결정한다.

```sql
CREATE TABLE ml_projections (
    id                  SERIAL PRIMARY KEY,
    commodity_id        VARCHAR(20)  NOT NULL REFERENCES commodities(commodity_id),
    segment_id          VARCHAR(10)  NOT NULL REFERENCES segments(segment_id),
    period              DATE         NOT NULL,

    model_name          VARCHAR(20)  NOT NULL,  -- 'isolation_forest' | 'lof' | 'ocsvm'
    projection_method   VARCHAR(20)  NOT NULL,  -- 'pca' | 'feature_direct' (OI-15 확정 후 채워짐)

    -- 2D 투영 좌표
    x_value             NUMERIC(12,6) NOT NULL,
    y_value             NUMERIC(12,6) NOT NULL,

    -- 축 레이블 (프론트엔드에서 축 이름 표시용)
    x_label             VARCHAR(50),            -- 예: 'PC1', 'transmission_rate'
    y_label             VARCHAR(50),            -- 예: 'PC2', 'zscore'

    -- 이상 점수 (결과맵 색상 강도용)
    anomaly_score       NUMERIC(10,6),
    is_anomaly          BOOLEAN,

    pipeline_run_id     INTEGER      REFERENCES pipeline_runs(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (commodity_id, segment_id, period, model_name, projection_method)
);

CREATE INDEX idx_ml_proj_commodity_segment_model
    ON ml_projections (commodity_id, segment_id, model_name);
```

---

## 배치 관리 테이블

### `pipeline_runs` — 월별 배치 실행 이력

배치 롤백·덮어쓰기 정책 (D-17):
- 각 Phase 적재는 단일 트랜잭션으로 묶는다.
- Phase 적재 실패 시 해당 Phase를 롤백하고 `status = 'failed'`로 기록한다. 이전 Phase까지의 데이터는 유지한다.
- 재실행은 `status = 'completed'`인 마지막 Phase 이후부터 재시작한다.
- 새 배치는 기존 완료 데이터를 덮어쓰는 방식(`INSERT ON CONFLICT DO UPDATE`)으로 적재한다.

```sql
CREATE TABLE pipeline_runs (
    id              SERIAL PRIMARY KEY,
    run_date        DATE         NOT NULL,          -- 배치 실행 날짜
    data_up_to      DATE         NOT NULL,          -- 적재된 데이터 기준 시점 (예: 2026-03-01)
    next_run_date   DATE,                           -- 다음 갱신 예정일 (data_freshness 연동)
    status          VARCHAR(20)  NOT NULL DEFAULT 'running',
    -- 'running' | 'completed' | 'failed'
    phases_run      VARCHAR(10)[],                  -- 실행된 Phase 목록 (예: {'0','1','2',...,'7-ml'})
    error_message   TEXT,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,

    UNIQUE (run_date)
);
```

---

### `data_freshness` — 데이터 기준 시점

웹 서비스 상단 바의 "2026년 3월 기준 · 다음 갱신 4월 15일 예정" 칩 컴포넌트 데이터 소스(web_plan_vN §3.3).

Redis 캐시 무효화 방향성 (D-18): 배치 완료 시 `pipeline_runs.id`를 Redis 캐시 키에 포함하여 갱신 여부를 판단하는 방식을 예비 방향으로 기록한다. 상세 규칙(TTL, 키 네이밍 규칙)은 OI(캐시 키 규칙, S6 결정) 해소 시 확정한다.

```sql
CREATE TABLE data_freshness (
    id              SERIAL PRIMARY KEY,
    data_up_to      DATE         NOT NULL,          -- 현재 데이터 기준 시점
    next_run_date   DATE         NOT NULL,          -- 다음 갱신 예정일
    last_updated    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    pipeline_run_id INTEGER      REFERENCES pipeline_runs(id)
);
-- 항상 최신 1개 행만 유지
```

---

## 집계 뷰

### `mv_anomaly_density_yearly` — 연도별 이상 밀도 머티리얼라이즈드 뷰 (D-08)

미니맵(web_plan_vN §4.1) `anomaly_density` 데이터 소스. `pipeline_runs` 완료 후 `REFRESH MATERIALIZED VIEW`로 갱신한다.

```sql
CREATE MATERIALIZED VIEW mv_anomaly_density_yearly AS
SELECT
    commodity_id,
    segment_id,
    EXTRACT(YEAR FROM period)::SMALLINT     AS year,
    COUNT(*) FILTER (WHERE confidence_grade = 'high')      AS high_count,
    COUNT(*) FILTER (WHERE confidence_grade = 'medium')    AS medium_count,
    COUNT(*) FILTER (WHERE confidence_grade = 'reference') AS reference_count
FROM anomaly_results
GROUP BY commodity_id, segment_id, EXTRACT(YEAR FROM period)
WITH DATA;

CREATE UNIQUE INDEX idx_mv_anomaly_density
    ON mv_anomaly_density_yearly (commodity_id, segment_id, year);
```

갱신 시점: 각 `pipeline_runs` 완료(`status = 'completed'`) 후 즉시 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_anomaly_density_yearly` 실행.

---

## API 엔드포인트 ↔ 테이블 대응

web_plan_vN §12의 API 엔드포인트별로 주로 참조하는 테이블을 정리한다.

| API 엔드포인트 | 주 참조 테이블 | 보조 참조 테이블 |
|---|---|---|
| `GET /api/commodities/{id}/stream` | `stat_timeseries` (전이율 곡선) | `anomaly_results` (이상 노드) |
| `GET /api/commodities/{id}/stream/minimap` | `mv_anomaly_density_yearly` (밀도 집계) | `stat_timeseries` (전이율 연별 집계) |
| `GET /api/commodities/{id}/scatter` | `stat_timeseries` (upstream_pct, downstream_pct) | `anomaly_results` (이상 노드 색상) |
| `GET /api/commodities/{id}/raw-prices` | `raw_prices` | `anomaly_results` (이상 노드 오버레이) |
| `GET /api/events` | `external_events` | — (프론트엔드가 클라이언트에서 시계열에 오버레이) |
| `GET /api/anomalies/summary` | `anomaly_results` (is_new, 이달 이상 목록) | `data_freshness` |
| `GET /api/anomalies/{id}/detail` | `anomaly_results`, `baselines`, `asymmetry_results` | `cointegration_results`, `stat_timeseries`, `ml_scores` |
| `GET /api/anomalies/{id}/stat-series` | `stat_timeseries` | `breakpoints.bp_dates` (구조 변화 수직선) |
| `GET /api/anomalies/{id}/stat-snapshot` | `stat_timeseries` (IQR), `asymmetry_results` (비대칭) | — |
| `GET /api/anomalies/{id}/irf` | `irf_data` | `subperiods` (하위 기간 레이블) |
| `GET /api/anomalies/{id}/ml-map` | `ml_projections` | — |
| `GET /api/commodities/{id}` | `baselines` (warmup_end, 전체 기간 기준선) | `cointegration_results` |

---

## 미결 사항 및 검수 체크리스트

### 파이프라인 출력 확정 후 검수 필요 항목

| 항목 | 현재 상태 | 검수 기준 |
|---|---|---|
| `ml_projections.projection_method` | `pca` / `feature_direct` 양방향 수용 구조로 설계 | OI-15 확정(S4) 후 불필요한 경우 단순화·저장 범위 축소 검토 |
| `anomaly_results.pattern_types` | 배열 타입으로 복수 패턴 허용, UNIQUE 1행 집계 | Phase 7 실제 출력에서 동월 복수 패턴 발생 여부 확인 |
| `stat_timeseries.zscore_w36/w60` | 로버스트니스용 컬럼 사전 정의 | Phase 8 로버스트니스 결과 노출 여부 확정 후 불필요 시 제거 |
| `breakpoints.bp_dates` | PostgreSQL DATE 배열 사용 | 최대 변화 시점 수 확인 후 jsonb로 전환 검토 |
| `irf_data.horizon` | 0~24개월 범위 가정 | Phase 4 IRF 산출 최대 horizon 확인 후 조정 |
| `subperiods` 참조 관계 | `model_params`, `baselines`, `irf_data`에서 FK 참조 | Phase 6 구현 후 하위 기간 분할 실제 발생 여부 확인 |
| `mv_anomaly_density_yearly` 갱신 성능 | CONCURRENTLY 갱신 예정 | 실제 데이터 크기(10 품목 × 5 구간 × 26년) 기준 측정 후 확정 |

### 과적재 후 축소 검토 대상 컬럼

파이프라인 출력 확정 후 실제 사용 여부를 확인하여 제거를 검토할 컬럼 목록.

| 테이블 | 컬럼 | 제거 조건 |
|---|---|---|
| `stat_timeseries` | `zscore_w36`, `zscore_w60` | Phase 8 로버스트니스 결과가 웹에 미노출로 확정될 경우 |
| `stat_timeseries` | `spread_n2`, `spread_n6` | 웹에서 N=3 단일 기준만 표시하는 것으로 확정될 경우 |
| `anomaly_results` | `actual_lag`, `normal_lag` | 패턴 1 세부 지표가 패널에 미노출로 확정될 경우 |
| `ml_projections` | `x_label`, `y_label` | 축 레이블을 프론트엔드 코드에 하드코딩하기로 확정될 경우 |
| `model_params` | `aic`, `bic`, `log_likelihood` | 모형 적합도 지표가 웹·논문 어디에도 미사용으로 확정될 경우 |

---

*v5 — 당시 pipeline_output_spec v6 반영. Phase 3~7 미구현 구간 테이블은 당시 pipeline_output_spec v6 기준 설계. 파이프라인 구현 완료 후 실제 출력과 대조하여 갱신 필요. (v5에서 외부 참조 표기를 `abcd_vN.md` 규칙으로 전환, `docs/docs_manifest.md` 버전 해석기 연동)*
