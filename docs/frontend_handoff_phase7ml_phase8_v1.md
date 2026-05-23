# Frontend 핸드오프 — Phase 7-ML · Phase 8 통합 협의

**문서 유형**: 백엔드 → 프론트엔드 협의 문서 (v1)
**작성일**: 2026-05-23
**작성자**: 백엔드 팀
**대상**: 프론트엔드 팀
**상태**: 초안 / 협의 대기

---

## 0. 문서 목적

파이프라인 리포(`price-transmission-lab-sunmoon/price-transmission`)의 `develop` 브랜치에 **Phase 7 통계 탐지 안정화 / Phase 7-ML 확정 / SHAP 분석 / 5축 평가 / Phase 8(메타 분석) 신규 산출**이 반영되었다. 이로 인해 백엔드에 적재 격차 + 프론트엔드 신규 컴포넌트 요구가 발생한다.

본 문서는:

1. 백엔드의 현재 ML/Phase 8 통합 상태와 격차를 공유한다.
2. 파이프라인 `develop` 브랜치에서 확인한 신규 산출물을 정리한다.
3. 프론트엔드에 요구되는 신규/변경 작업과 결정 필요 사항을 제시한다.
4. 양 팀의 후속 작업 우선순위를 합의한다.

---

## 1. 파이프라인 `develop` 브랜치 최근 변경 (2026-05-20 ~ 05-23)

### 1.1 신규/갱신된 루트 문서

| 파일 | 의미 |
|---|---|
| `README_Phase7_stat_.md` | Phase 7 통계 탐지(패턴 1·2·3) 명세 |
| `README_Phase7_ML.md` | Phase 7-ML 명세 + SHAP 결과 + 5축 평가 결과 |
| `README_Phase8.md` | Phase 8 메타 분석 명세 (신규) |
| `docs/phase7_threshold.md` | Phase 7 임계값(W=48, Z=2.5, IQR×1.5, ±3%, 0.5%, 1.0%) 근거 |

### 1.2 최근 3일 커밋

| 일자 | 커밋 | 내용 |
|---|---|---|
| 2026-05-23 | `befdf89` | Merge PR #4 (pipeline → develop) |
| 2026-05-22 | `56115b6` | Phase 8 코드 + Readme (Yebs697) |
| 2026-05-21 | — | output-dir 인자 추가, run_meta.json 상태 기록, 히트맵 구체화, 정규화 자료 |
| 2026-05-20 | `50d1cc5`, `fe1e47c` | 히트맵 개선(이상치 필터·툴팁), beeswarm 추가 |

→ Phase 7-ML 본체는 안정화. 최근 작업은 **시각화(SHAP 대시보드 + heatmap + beeswarm) + Phase 8 신규**.

### 1.3 신규 디렉토리

```
src/preprocessing/
├── Phase7/
│   └── phase7_ml_visualize.py        ← 신규 시각화 코드
└── phase8/                            ← 신규 전체 디렉토리
    ├── phase8_run.py
    ├── phase8_common.py
    ├── phase8_summary.py
    ├── phase8_robustness.py
    └── phase8_5_synchrony.py

tests/
├── phase7_ml/                         ← 5축 평가 신규
│   ├── eval_common.py
│   ├── run_all_evaluation.py
│   ├── generate_dashboard.py
│   └── test_axis1_esr.py ~ test_axis5_consensus.py
└── shap/                              ← SHAP 분석 신규
    ├── run_shap_if.py
    ├── run_shap_lof.py
    ├── run_shap_svm.py
    └── generate_shap_dashboard.py
```

---

## 2. 파이프라인 신규 산출물 상세

### 2.1 Phase 7-ML 본체 (확정 명세)

`pipeline_output_spec_v9 §Phase 7-ML`와 일치. 변경 없음.

**확정 파라미터** (코드 기준 하드코딩, `config/settings.py` 미반영):

| 모델 | 파라미터 | 값 |
|---|---|---|
| Isolation Forest | n_estimators / contamination / random_state | 100 / **0.08** / 42 |
| LOF | n_neighbors / contamination / novelty | 10 / **0.08** / False |
| One-Class SVM | kernel / nu / gamma | rbf / **0.08** / scale |
| 전처리 | scaler | StandardScaler |
| 앙상블 | consensus_threshold | 2 (3종 중 2개 이상) |

**6 피처(고정)**: `transmission_rate`, `upstream_pct`, `downstream_pct`, `ect_or_spread`, `exchange_rate_pct`, `intl_price_usd_pct`

**출력**: `data/processed/phase7_ml/{features,predictions,cross_validation,confidence_grades}/` + `models/{YYYYMMDD_HHMM}/` (joblib pkl + `run_log_*.json`) + `phase7_ml_summary.csv`

**중요**: predictions CSV에 `*_score`는 있으나 **`*_percentile`은 산출되지 않는다** (백엔드 적재 시 산출 또는 명세 외 항목으로 결정 필요).

### 2.2 SHAP 분석 (신규)

3종 모델 각각의 피처 중요도. `tests/shap/results/{YYYYMMDD_HHMM}_{IF|LOF|SVM}/` 및 `대시보드_{YYYYMMDD_HHMM}/` 산출.

**글로벌 피처 중요도 (Mean |SHAP|, 정규화 %)**:

| 피처 | IF | LOF | SVM |
|---|---:|---:|---:|
| `intl_price_usd_pct` | **18.4** | 13.5 | 17.2 |
| `exchange_rate_pct` | 17.0 | 15.7 | 17.0 |
| `transmission_rate` | 16.9 | **21.8** | 16.0 |
| `ect_or_spread` | 16.4 | 12.3 | **19.6** |
| `downstream_pct` | 16.2 | 20.9 | 13.0 |
| `upstream_pct` | 15.8 | 15.9 | 16.5 |

모델별 1순위가 다르다 → 3종 앙상블의 상호 보완성 근거.

**산출 파일**:
- `{cid}_{seg}_shap.csv` × 20 유닛: 관측치별 6피처 SHAP 값
- `shap_summary.csv`: 유닛별 top 피처 + 중요도
- `run_meta.json`: explainer, status(complete/partial), global_feature_importance

### 2.3 5축 평가 프레임워크 (신규)

ML에 라벨이 없어 정확도·재현율을 산출할 수 없으므로 5개 독립 축으로 신뢰성을 다면 평가.

| 축 | 지표 | 값 | 판단 |
|---|---|---|---|
| 1 | ESR (외부 충격 회수율) | 0.516 | 중간 |
| 2 | SR (이상 점수 분리도) IF/LOF/SVM | 2.71 / 2.61 / 2.22 | 양호 (전부 >2.0) |
| 3 | Stat-ML AUC (연속형 앙상블) | 0.607 | 독립-일관 범위 |
| 4 | 안정성 (contam / LOF k) | 0.725 / 0.924 | 중간 / 강건 |
| 5 | 합의 가설 (ASC > 개별 P) | 7/20 (35%) | 부분 성립 |

산출: `tests/phase7_ml/results/run_{YYYYMMDD_HHMMSS}/{axis1~5}.csv` + `axis3_roc_curves.json` + `run_meta.json`. `results/latest/`에 최신 결과 복사본.

### 2.4 Phase 8 (신규, 메타 분석)

**입력**: Phase 7, Phase 7-ML, Phase 4 baseline, Phase 6 breakpoints, Phase 1 changes/robustness

**출력**: 16 CSV + 2 JSON, ~280 KB. **DB 결합 없음** (README_Phase8.md 명시: "웹 대시보드는 향후 작업, Phase 8 output을 DB에 적재 필요")

#### Summary (S1~S5) — `data/processed/phase8/summary/`

| 파일 | 핵심 컬럼 | 의미 |
|---|---|---|
| `confidence_summary.csv` | commodity_id, segment, total_anomalies, high, medium, reference, high_pct, stat_only, ml_only | 신뢰도 등급 집계 + 합산 행 |
| `agreement_analysis.csv` | both_detected, stat_only, ml_only, both_normal, agreement_rate, **cohen_kappa** | 통계·ML 일치도 |
| `cross_commodity_comparison.csv` | p1_count/rate, p2_count/rate, p3_count/rate, total_stat, ml_detected, high_count, has_wholesale | 품목 × 구간 패턴 비율 |
| `wholesale_comparison.csv` | group, avg_p1_rate_A/B, avg_p2_rate_A/B, avg_stat_rate_A/B, avg_high_pct | 3구간 vs 4구간 그룹 평균 |
| `wholesale_downstream_analysis.csv` | upstream_count, downstream_count, co_occurrence, downstream_follows_1m/3m | 4구간 품목 A·B → C·D 전파 |
| `shock_correspondence.csv` | shock_id, shock_name, shock_start/end, n_applicable_segments, **stat_recall**, **ml_recall**, high_hits | 외부 충격 5종(E1·E6·E9·E2·E4) 회수율 |
| `shock_detail.csv` | shock_id × (commodity, segment) 단위 detail | 충격별 유닛 응답 detail |

#### Robustness (R1~R3) — `data/processed/phase8/robustness/`

| 파일 | 핵심 컬럼 |
|---|---|
| `rolling_window_sensitivity.csv` | w36/w48/w60_flags, w36_w48_jaccard, w48_w60_jaccard, **stability_verdict** |
| `seasonal_method_comparison.csv` | stl_flags, dummy_flags, overlap, jaccard, stability_verdict |
| `contamination_sensitivity.csv` | c005/c008/c010/c012/c015_detected, ×_c008_jaccard, stability_verdict |
| `robustness_summary.json` | 3종 평균 Jaccard + 종합 verdict |

`stability_verdict`: `stable`(≥0.7) / `moderate`(0.4~0.7) / `sensitive`(<0.4)

#### Synchrony (T1~T6) — `data/processed/phase8/synchrony/`

| 파일 | 핵심 컬럼 |
|---|---|
| `heatmap_data.csv` (**5,372 행**) | date, commodity_id, segment, pattern_type, confidence_grade, stat_detected, ml_detected |
| `monthly_co_detection.csv` | 월별 동시 탐지 품목 수 + 충격창 매핑 |
| `case_A_ukraine.csv` | E4 wheat/maize/soybean 구간 A 타임라인 |
| `case_B_russia_drought.csv` | E6 7품목 구간 A |
| `case_C_feed_livestock.csv` | maize/soybean A → beef A 1m/3m/6m 시차 |
| `ml_reference_co_occurrence.csv` | k≥3 품목이 동시 reference 등급 |

#### 메타

`phase8_meta.json`: 실행 시각, 입력 파일 체크섬, 파라미터 로그

---

## 3. 백엔드 현황 (ML/Phase 8 통합 상태)

### 3.1 ML 슬롯: 이미 준비되었으나 적재가 비어있는 영역

| 영역 | 위치 | 상태 | 비고 |
|---|---|---|---|
| ORM `MLScore` (`ml_scores`) | `app/db/models/anomaly.py:273` | 테이블·컬럼 있음 | **적재 없음** — `if_score`/`lof_score`/`svm_score`/percentile 전부 비어있음 |
| ORM `MLProjection` (`ml_projections`) | `app/db/models/anomaly.py:309` | 테이블·컬럼 있음 | **OI-15 보류** — `projection_method` 미확정 |
| ORM `AnomalyResult.ml_*` | `:60` | `if_anomaly`/`lof_anomaly`/`svm_anomaly`/`ml_vote`/`ml_detected`/`confidence_grade` 적재됨 | 정상 |
| Pydantic `MLSummary` | `app/schemas/anomaly.py:82` | `*_score`, `*_percentile` 필드 존재 | `MLScore` 미적재로 인해 항상 null |
| API `/anomalies/{id}/detail` | `app/services/anomaly_panel.py:130` | `MLScore` 조회 후 `MLSummary` 채움 | ML 점수 항상 null |
| API `/anomalies/{id}/ml-map` | `:583` | `MLProjection` 조회. 없으면 빈 응답 fallback | 빈 응답 |
| 적재 스크립트 | 루트 `load_phase7.py` (수동) | `stat_timeseries`, `anomaly_results` 적재 OK | **`ml_scores` 적재 누락** |
| Batch flow | `app/services/batch.py` | Phase 7/7-ml **skip 상태** | README §배치 흐름: "phase7-stat 구현 완료 후 연결" |

### 3.2 Phase 8: 백엔드 미반영 (전체)

- DB 스키마: phase8 관련 테이블 **0건**
- ORM 모델: 없음
- API 엔드포인트: 없음
- 적재 로직: 없음
- 명세 문서(`db_schema_v6.md`, `api_spec_v6.md`, `pipeline_output_spec_v9.md`): Phase 8 부록 없음

---

## 4. 프론트엔드 영향 분석

### 4.1 기존 ML 컴포넌트가 채워질 예정 (대부분 추가 작업 불필요)

`/anomalies/{id}/detail` 응답의 `ml_summary` 항목들이 `ml_scores` 적재 후 **null → 실제 값**으로 바뀔 뿐, 응답 스키마 자체는 변경 없음. 프론트엔드는 기존 표시 로직 그대로 동작한다.

```jsonc
// 적재 전 (현재)
"ml_summary": {
  "ml_vote": 2, "ml_detected": true,
  "if_anomaly": true, "if_score": null, "if_percentile": null,
  "lof_anomaly": true, "lof_score": null, "lof_percentile": null,
  "svm_anomaly": false, "svm_score": null, "svm_percentile": null
}

// 적재 후 (예정)
"ml_summary": {
  "ml_vote": 2, "ml_detected": true,
  "if_anomaly": true, "if_score": -0.0421, "if_percentile": 3.2,
  ...
}
```

⚠ `*_percentile` 산출 방식 미정 → 잠정 null 유지될 수 있다.

### 4.2 `/anomalies/{id}/ml-map`: 보류 유지 (현재와 동일)

`projection_method`(`pca` / `feature_direct`) 확정 전까지 빈 응답 fallback 유지. 프론트엔드에 ML 결과맵 시각화가 필요한 경우 별도 협의.

### 4.3 Phase 8 신규 UI/엔드포인트 후보 (협의 필요)

Phase 8 산출물을 어떻게 노출할지에 따라 프론트엔드 작업량이 크게 달라진다. 다음은 후보 매핑이다:

| Phase 8 산출 | 프론트엔드 UI 후보 | API 후보 |
|---|---|---|
| `confidence_summary` | 신뢰도 등급 분포 막대 (전체/품목별) | `/meta/confidence-summary` |
| `agreement_analysis` (Cohen κ) | 통계·ML 일치도 표/지표 카드 | `/meta/agreement` |
| `cross_commodity_comparison` | 품목 × 구간 패턴 비율 표/매트릭스 | `/commodities/comparison` |
| `wholesale_comparison`, `wholesale_downstream_analysis` | 3구간 vs 4구간 그룹 비교 카드 + 시차 표 | `/meta/wholesale-analysis` |
| `shock_correspondence`, `shock_detail` | 외부 충격 5종 × 회수율 표 + 충격 detail 모달 | `/events/{key}/recall`, `/events/{key}/detail` |
| `rolling_window_sensitivity`, `seasonal_method_comparison`, `contamination_sensitivity` | 강건성 검토 패널 (stable/moderate/sensitive 색상 코딩) | `/meta/robustness?type=...` |
| `heatmap_data` (5,372행) | 시간 × 품목 히트맵 (메인 시각화 후보) | `/commodities/heatmap` 또는 stat_timeseries 흡수 |
| `monthly_co_detection` | 월별 동시 탐지 품목 수 라인 차트 | `/meta/co-detection` |
| `case_A/B/C_*` | 케이스 스터디 페이지 (Ukraine/Russia/Feed-Livestock) | `/meta/case-studies/{key}` |
| `ml_reference_co_occurrence` | ML-only 동시 탐지 클러스터 (참고 신호) | `/anomalies/ml-reference-cluster` |
| 5축 평가 | 모델 신뢰성 카드 (ESR / SR / AUC / 안정성 / 합의) | `/meta/ml-evaluation` |
| SHAP 글로벌 중요도 | 피처 중요도 막대 (모델별 3 series) | `/meta/ml-shap` |

### 4.4 명세 문서 영향

다음 백엔드 명세는 Phase 7-ML 적재 완료 + Phase 8 통합 결정 후 갱신이 필요하다. 프론트엔드 명세(`frame_spec_frontend_vN`)도 동기 갱신 필요.

| 백엔드 명세 | 갱신 필요 항목 |
|---|---|
| `db_schema_v6.md` | `ml_shap_importance`, `ml_evaluation_run`, `phase8_*` 신규 테이블 |
| `api_spec_v6.md` | `/meta/ml-shap`, `/meta/ml-evaluation`, `/meta/phase8/*` 신규 엔드포인트 |
| `pipeline_output_spec_v9.md` | Phase 8 출력 부록 + SHAP/5축 산출 부록 |
| `frame_spec_frontend_v5.md` | 신규 화면/컴포넌트 정의 (Phase 8 UI 결정에 따라) |
| `web_plan_v6.md` | Phase 8 UI 배치 (메인/패널/별도 페이지 결정) |

---

## 5. 협의가 필요한 결정 항목

다음 항목은 양 팀(+ 파이프라인 팀) 합의 후 작업 착수가 가능하다.

### 5.1 Phase 7-ML 적재 범위

- **Q1**: `*_percentile` 산출을 어디서? (선택지)
  - 백엔드 적재 시점에 segment 내 점수 분포로 산출
  - 파이프라인 측 `phase7_ml_models.py`에 percentile 컬럼 추가 요청
  - 일단 NULL 유지 (프론트엔드는 미표시)
- **Q2**: `ml_projections`(OI-15) projection_method 확정 시점?
- **Q3**: Phase 7-ML 적재(트랙 A) 작업을 Phase 8 협의보다 먼저 진행할지?

### 5.2 Phase 8 노출 범위

- **Q4**: 16개 Phase 8 CSV 중 DB 적재할 항목은? (전부 / 핵심만 / 정적 파일 서빙)
- **Q5**: `heatmap_data.csv`(5,372행)는 신규 `phase8_heatmap` 테이블 vs 기존 `stat_timeseries` 흡수?
- **Q6**: 케이스 스터디(case_A/B/C)는 동적 API vs 정적 JSON?
- **Q7**: 5축 평가 + SHAP을 메타 엔드포인트(`/meta/ml-*`)로 통합 vs 별도 `/insights/*` 네임스페이스?

### 5.3 SHAP/5축 적재

- **Q8**: SHAP 결과는 `run_meta.json`의 글로벌 importance만 적재 vs 유닛별 `{cid}_{seg}_shap.csv` 전부 적재?
- **Q9**: 5축 평가는 최신 1건만 vs 실행 이력 전체 보관?

### 5.4 데이터 신선도

- **Q10**: Phase 8 산출은 월 배치 일괄 vs 별도 트리거? (Phase 7-ML 완료 후 자동 실행 권장)

### 5.5 명세 갱신 책임 분담

- **Q11**: 백엔드/프론트엔드 명세 갱신을 동시 진행 vs 백엔드 선행 후 프론트엔드?

---

## 6. 제안 로드맵 (협의 후 확정)

### 옵션 A — 최소 (Phase 7-ML 본체만)

1. 백엔드: `ml_scores` 적재 + batch flow 연결 (트랙 A)
2. 프론트엔드: 추가 작업 거의 없음 (기존 `ml_summary` 표시가 채워짐)
3. Phase 8 / SHAP / 5축 → 별도 세션

**기간**: 백엔드 ~2일, 프론트엔드 ~0.5일 (검증만)

### 옵션 B — 중간 (Phase 7-ML + SHAP + 5축)

1. 옵션 A + `ml_shap_importance`, `ml_evaluation_run` 테이블 + `/meta/ml-shap`, `/meta/ml-evaluation` 신설
2. 프론트엔드: 모델 신뢰성 카드 + SHAP 피처 중요도 막대 신규 컴포넌트
3. 명세 갱신: `db_schema_v7`, `api_spec_v7`

**기간**: 백엔드 ~3일, 프론트엔드 ~2일

### 옵션 C — 전체 (+ Phase 8)

1. 옵션 B + Phase 8 핵심 6~9개 테이블 + `/meta/phase8/*` 또는 분산 엔드포인트
2. 프론트엔드: 히트맵·신뢰도 분포·외부 충격 회수율·강건성 패널 신규
3. 명세 전면 갱신 + `web_plan_v7`

**기간**: 백엔드 ~7일, 프론트엔드 ~5일

### 옵션 D — 명세 우선 (구현 보류)

1. `db_schema_v7`, `api_spec_v7`, `pipeline_output_spec_v10`, `frame_spec_frontend_v6` 갱신 선행
2. 결정 항목(§5) 전부 합의 후 구현 착수

**기간**: 문서 ~3일, 구현은 옵션 A/B/C 중 선택 후 추가

---

## 7. 다음 단계 (제안)

1. **백엔드·프론트엔드·파이프라인 3자 협의** — 본 문서를 기반으로 §5 결정 항목 합의
2. **옵션 선택** — A/B/C/D 중 결정
3. **명세 갱신 PR** — 합의 결과를 `db_schema_vN+1`, `api_spec_vN+1`, `pipeline_output_spec_vN+1`, `frame_spec_*_vN+1`에 반영
4. **구현 PR** — 결정된 옵션에 따라 백엔드·프론트엔드 병행

---

## 8. 참고 자료

### 8.1 파이프라인 리포 (price-transmission-lab-sunmoon/price-transmission, develop)

- `README_Phase7_stat_.md`
- `README_Phase7_ML.md`
- `README_Phase8.md`
- `docs/phase7_threshold.md`
- `src/preprocessing/Phase7/phase7_ml_run.py`, `phase7_ml_visualize.py`
- `src/preprocessing/phase8/phase8_run.py`, `phase8_summary.py`, `phase8_robustness.py`, `phase8_5_synchrony.py`, `phase8_common.py`
- `tests/phase7_ml/`, `tests/shap/`

### 8.2 백엔드 리포 관련 파일

- `app/db/models/anomaly.py` (MLScore, MLProjection, AnomalyResult)
- `app/schemas/anomaly.py` (MLSummary)
- `app/services/anomaly_panel.py` (/detail, /ml-map)
- `load_pipeline_outputs.py`, `load_phase7.py` (수동 적재 스크립트)
- `app/services/batch.py` (배치 흐름, Phase 7/7-ml skip 표기)
- `docs/pipeline_output_spec_v9.md` §Phase 7-ML
- `docs/db_schema_v6.md` §ml_scores, §ml_projections
- `docs/api_spec_v6.md` §/anomalies/{id}/detail, §/anomalies/{id}/ml-map

---

_v1 (2026-05-23) — 초안. §5 결정 항목 합의 후 v2로 갱신 예정._
