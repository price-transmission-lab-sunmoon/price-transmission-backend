# 백엔드 → 프론트엔드 회신 — Phase 7-ML 적재 합의

**작성일**: 2026-05-24
**작성자**: 백엔드 (바게스타니 샤킬라)
**대상**: 프론트엔드 (하대수)
**참조**:
- `docs/frontend_handoff_phase7ml_phase8_v1.md` (백엔드 → 프론트, 2026-05-23)
- 프론트엔드 회신 (2026-05-23)
**상태**: 합의안 / PR 착수 대기

---

## 0. 결론 요약

| 항목 | 결정 |
|---|---|
| 작업 범위 | **옵션 A — Phase 7-ML 본체 적재만**. Phase 8 / SHAP / 5축 미적용. |
| Q1 percentile 산출 | **A — 백엔드 적재 시점 산출** (`rank(pct=True)*100`, segment 단위) |
| Q2 projection_method | **`pca`** 채택. `x_label="PC1"`, `y_label="PC2"` 고정. |
| 응답 스키마 불변 | **확약**. `MLSummary` 11 필드 외 추가/삭제/이름 변경 금지. 변경 사유 발생 시 사전 협의. |
| 일정 | 본 회신일 기준 ② 2일 + ③ 1일 (병행 가능). 명세 갱신 PR 병행. |

→ 프론트엔드 회신 §6 요청 4건 모두 확정 회신.

---

## 1. Q1 회신 — `*_percentile` 산출 위치: 옵션 A (백엔드 산출)

### 1.1 채택 사유

- 파이프라인 측 변경 불필요 → 협업 지연 없음.
- 사용자(엔드유저) 정보량 최대 (NULL 미발생).
- 적재 시점에 segment 내 점수 분포가 이미 메모리상 존재 → 추가 비용 미미.

### 1.2 산출 규칙

**기본 정의**: 동일 `(commodity_id, segment_id)` 그룹 내에서, 각 점수 컬럼별로 백분위(0~100) 산출.

| 컬럼 | 산출식 | 의미 |
|---|---|---|
| `if_percentile` | `df.groupby([cid,seg])["if_score"].rank(pct=True) * 100` | IF score는 낮을수록 이상 → 낮은 percentile = 더 이상 |
| `lof_percentile` | `df.groupby([cid,seg])["lof_score"].rank(pct=True) * 100` | LOF score 동일 |
| `svm_percentile` | `df.groupby([cid,seg])["svm_score"].rank(pct=True) * 100` | SVM decision_function 음수=이상 → 낮은 percentile = 더 이상 |

**구현 위치**: `app/db/loader/phase7_ml.py` (신규). predictions CSV 로드 후 적재 직전 산출.

**Tie 처리**: pandas `rank` 기본값(`method='average'`) 사용 — 동점 시 평균 순위.

**NULL 처리**: 점수 자체가 NULL인 행은 percentile도 NULL.

### 1.3 프론트엔드 영향

- `ml_summary.if_percentile / lof_percentile / svm_percentile` 항상 `number` 또는 `null`. **신규 NaN/Inf 발생 없음**.
- UI 표시 의미 — 백분위 낮을수록 "이상도 강함". 프론트 측 라벨링이 필요한 경우 별도 회신 부탁.

---

## 2. Q2 회신 — `projection_method`: `pca` 채택

### 2.1 채택 사유

- 프론트 fixture (`panel_ml_map_*.json`) + 훅 기본값 (`useMLMap.ts`) 일치 — 프론트 코드 변경 0.
- SHAP 글로벌 중요도 검토 결과 6피처 간 중요도 차이가 평탄 (16~18% 범위) → 특정 2피처 선택의 근거 약함.
- `feature_direct`는 향후 협의 시 별도 옵션으로 추가 가능 (literal 타입에 이미 존재).

### 2.2 산출 규칙

**입력**: `data/processed/phase7_ml/features/{cid}_{seg}_features.csv` 6피처 (`transmission_rate`, `upstream_pct`, `downstream_pct`, `ect_or_spread`, `exchange_rate_pct`, `intl_price_usd_pct`)

**전처리**: `phase7_ml_run.py`와 동일하게 `StandardScaler` 적용 (결측 행 제외).

**투영**:
```python
from sklearn.decomposition import PCA
pca = PCA(n_components=2, random_state=42)
xy = pca.fit_transform(X_scaled)  # (n_obs, 2)
```

**좌표 매핑**:
- `x_value = xy[:, 0]`, `y_value = xy[:, 1]`
- `x_label = "PC1"`, `y_label = "PC2"` 고정

**모델별 적재 규칙** (3 행 / 관측치):

| `model_name` | `anomaly_score` 출처 | `is_anomaly` 출처 |
|---|---|---|
| `isolation_forest` | predictions.`if_score` | predictions.`if_anomaly` |
| `lof` | predictions.`lof_score` | predictions.`lof_anomaly` |
| `ocsvm` | predictions.`svm_score` | predictions.`svm_anomaly` |

→ 동일 `(cid, seg, period)` × 3 model_name = 3행. 좌표는 동일, score만 모델별 상이.

**UNIQUE 제약**: `(commodity_id, segment_id, period, model_name, projection_method)` — 기존 ORM 일치 (`app/db/models/anomaly.py:336`).

### 2.3 프론트엔드 영향

- 응답 shape — 회신 §2.3 명세 그대로. **변경 없음**.
- `points[].is_highlight` 산출: 패널이 조회한 anomaly의 `period`와 일치하는 점 1개를 `true`로 설정. 나머지 `false`.
- `feature_direct` 옵션은 본 PR에서 미구현. 호출 시 빈 응답 fallback 유지.

---

## 3. 일정

| 단계 | 담당 | 산출 | 예상 |
|---|---|---|---|
| ① 본 회신 검토 + 합의 확정 | 양 팀 | 합의 완료 | 즉시 |
| ② `app/db/loader/phase7_ml.py` 신설 + `ml_scores` 적재 + percentile 산출 + runner 등록 + batch flow 연결 | 백엔드 | PR | 2일 |
| ③ `ml_projections` 적재 (PCA 산출) + `/ml-map` 활성화 | 백엔드 | PR (②와 분리 가능) | 1일 |
| ④ 명세 갱신 PR — `api_spec_vN+1`, `db_schema_vN+1` | 백엔드 | PR | ②와 병행 |
| ⑤ 프론트 통합 검증 (`VITE_USE_MOCK=false`) | 프론트 | 회신 | 0.5일 |
| ⑥ `load_phase7.py` 루트 → `app/db/loader/phase7.py` 이전 (정리) | 백엔드 | ② PR에 포함 | (②에 포함) |

**병합 순서 권장**: ② → ⑤(부분) → ③ → ⑤(완료) → ④

---

## 4. 응답 스키마 불변 확약

### 4.1 `MLSummary` 11 필드 — 변경 금지

```jsonc
{
  "ml_vote":         number,            // 0~3
  "ml_detected":     boolean,
  "if_anomaly":      boolean | null,
  "if_score":        number  | null,
  "if_percentile":   number  | null,    // 본 PR로 number 채워짐 (Q1-A)
  "lof_anomaly":     boolean | null,
  "lof_score":       number  | null,
  "lof_percentile":  number  | null,
  "svm_anomaly":     boolean | null,
  "svm_score":       number  | null,
  "svm_percentile":  number  | null
}
```

- 필드 추가/삭제/이름 변경 시 본 협의 채널로 사전 통지.
- snake_case 유지. camelCase 변환 금지.
- 값 도메인: NaN / Inf 송신 금지 (`load_phase7.py`와 동일하게 NULL로 변환).

### 4.2 `/ml-map` 응답 shape — 프론트 회신 §2.3과 일치

- `model`: `'isolation_forest' | 'lof' | 'ocsvm'`
- `projection_method`: `'pca' | 'feature_direct'` (본 PR은 `pca`만)
- `x_label`, `y_label`: 본 PR `"PC1"`, `"PC2"` 고정.
- `points[].is_highlight`: 정확히 1개만 `true` (anomaly period와 동일한 점). 데이터 부재 시 0개.

---

## 5. Phase 8 / SHAP / 5축 — 본 협의 미적용 확정

프론트엔드 회신 §3 결정 수용:

- 백엔드 측에서도 신규 테이블 / 엔드포인트 / 적재 로직 일체 작업하지 않는다.
- 단, 파이프라인 산출 파일은 `data/processed/phase7_ml/`, `data/processed/phase8/`, `tests/phase7_ml/results/`, `tests/shap/results/`에 그대로 보존 — 논문 작성 및 향후 협의 시 즉시 활용 가능하도록 한다.
- 향후 정책 변경 시 별도 협의 문서로 재요청 절차 동의.

---

## 6. 명세 갱신 분담 — 프론트엔드 회신 §4 수용

| 문서 | 갱신 범위 | 담당 |
|---|---|---|
| `api_spec_vN+1.md` § /anomalies/{id}/detail `ml_summary` | "적재 후 number" 표기 갱신 | 백엔드 |
| `api_spec_vN+1.md` § /anomalies/{id}/ml-map | `projection_method=pca` 확정값 + `x_label/y_label` 고정값 명기 | 백엔드 |
| `db_schema_vN+1.md` § `ml_scores` | percentile 산출 정책(§1.2) 부록 추가 | 백엔드 |
| `db_schema_vN+1.md` § `ml_projections` | OI-15 해소 (pca 확정) 명기 | 백엔드 |
| `pipeline_output_spec_v9.md` | 변경 없음 — 파이프라인 측 변경 없음 | — |
| `frame_spec_frontend_v5.md` | 변경 없음 | — |
| `web_plan_v6.md` | 변경 없음 | — |
| Phase 8 관련 모든 명세 | 변경 없음 (본 협의 미적용 결정) | — |

→ 백엔드는 `api_spec_v7` + `db_schema_v7` (또는 차순 버전) 갱신 PR을 ② 작업과 함께 머지.

---

## 7. 후속 협의 채널

- 본 회신 + 프론트엔드 회신은 `docs/` 폴더에 영구 보존.
- ② PR 머지 시점에 프론트엔드에 알림 → 프론트 통합 검증 ⑤ 진행.
- 검증 중 응답 차이 발견 시 본 문서 v2로 갱신하여 합의 이력 유지.

---

## 8. 회신 요청 항목 — 합의 확정

프론트엔드 회신 §6 요청 4건 회신 완료:

1. ✅ **Q1 회신**: 옵션 A (백엔드 산출).
2. ✅ **Q2 회신**: `pca` 채택. `feature_direct`는 본 PR 미구현.
3. ✅ **일정**: ② 2일 + ③ 1일. 프론트 추정과 일치.
4. ✅ **스키마 불변 확약**: `MLSummary` 11 필드 유지. 변경 시 사전 협의.

본 합의안에 추가 의견이 없으면 ② 착수.

---

_v1 (2026-05-24) — 프론트엔드 핸드오프 v1 회신에 대한 백엔드 합의안._
