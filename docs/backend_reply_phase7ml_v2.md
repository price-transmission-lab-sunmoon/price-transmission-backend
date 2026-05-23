# 백엔드 → 프론트엔드 회신 v2 — Phase 7-ML 적재 합의 (최종)

**작성일**: 2026-05-24
**작성자**: 백엔드 (바게스타니 샤킬라)
**대상**: 프론트엔드 (하대수)
**참조**:
- `docs/frontend_handoff_phase7ml_phase8_v1.md` (백엔드 → 프론트, 2026-05-23)
- 프론트엔드 회신 v1 (2026-05-23)
- `docs/backend_reply_phase7ml_v1.md` (백엔드 → 프론트, 2026-05-24)
- 프론트엔드 회신 v2 (2026-05-24)
**상태**: 합의 최종 / ② PR 착수 준비

---

## 0. 결론 요약 — §1 / §2 회신

| 항목 | 결정 |
|---|---|
| §1 percentile 산출 방향 | **A 채택** — 백엔드 산출식 반전, "높은 percentile = 더 이상" |
| §1 LOF 산출식 | **정정 필요** — LOF도 IF/SVM과 동일하게 반전 (프론트 v2 §1.2 표의 LOF 행 정정) |
| §2 `*_anomaly` 타입 | **A 채택** — null 금지, 항상 `boolean` 송신 |

→ 본 회신으로 합의 완결. 백엔드 ② PR 착수.

---

## 1. §1 회신 — Percentile 산출 방향: A 채택 + LOF 정정

### 1.1 결정

**옵션 A 채택**: "높은 percentile = 더 이상" 의미로 통일. 프론트 현행 UI/fixture 의미 그대로 정합.

### 1.2 LOF 산출식 정정

프론트 v2 §1.2 표의 `lof_percentile` 행에 "LOF는 값 클수록 이상이므로 정방향(반전 X)" 표기가 있으나, 이는 sklearn 구현 사실과 다르다.

**소스 확인** (`pipeline/preprocessing/Phase7/phase7_ml_models.py:84`):
```python
model = LocalOutlierFactor(n_neighbors=10, contamination=0.08, novelty=False)
labels = model.fit_predict(X_scaled)
scores = model.negative_outlier_factor_   # ← 음수 또는 0 근처. 더 음수일수록 이상.
```

- sklearn `LocalOutlierFactor.negative_outlier_factor_`는 **이미 부호가 뒤집힌 LOF 값**. 정상 관측치는 -1 근처, 이상 관측치는 더 큰 음수(예: -3, -5). 즉 **`lof_score`(=negative_outlier_factor)는 "낮을수록(더 음수) 이상"** — IF/SVM과 방향 동일.

- `README_Phase7_ML.md`도 동일 명시:
  > "Anomaly scores (interpretation varies: IF/LOF lower=anomalous; SVM negative=anomalous)"

→ 3종 모두 **lower=anomalous** 통일. percentile 반전 식도 3종 동일.

### 1.3 최종 산출식 (합의안 §1.2 갱신)

| 컬럼 | 산출식 | 의미 |
|---|---|---|
| `if_percentile` | `(1 - df.groupby([cid,seg])["if_score"].rank(pct=True)) * 100` | 높은 percentile = 더 이상 (IF score 낮을수록 이상이므로 반전) |
| `lof_percentile` | `(1 - df.groupby([cid,seg])["lof_score"].rank(pct=True)) * 100` | 높은 percentile = 더 이상 (LOF `negative_outlier_factor_`는 더 음수일수록 이상이므로 IF와 동일 방향, 반전) |
| `svm_percentile` | `(1 - df.groupby([cid,seg])["svm_score"].rank(pct=True)) * 100` | 높은 percentile = 더 이상 (SVM `decision_function` 음수=이상이므로 반전) |

**핵심**: 모델별 score 방향 차이를 percentile 단에서 통일 → API 응답은 항상 "높을수록 이상"로 일관.

**Equivalent 표현** (구현 시 선택 가능, 결과 동일):
```python
# Option 1 — 반전식
pct = (1 - df.groupby([cid,seg])[score_col].rank(pct=True)) * 100

# Option 2 — ascending=False
pct = df.groupby([cid,seg])[score_col].rank(pct=True, ascending=False) * 100
```

### 1.4 Tie / NULL 처리 (재확인)

- pandas `rank` 기본값(`method='average'`) 사용 — 동점 시 평균 순위. 반전 후에도 동일 백분위.
- 점수 자체가 NULL인 행: percentile도 NULL.
- segment 내 관측치 1건만 있는 경우: rank=1.0 → 반전 후 0.0. 적재값 0.0 송신 (NULL 아님).

### 1.5 프론트엔드 영향

- 막대 길이 매핑(`barWidth = percentile`) 그대로 유효.
- 적재 결과 anomaly 행의 percentile은 일반적으로 90~99 구간에 분포. 직관과 일치.
- `confidence_grade='reference'`(ML만 탐지) 행의 percentile도 동일 규칙으로 산출됨.

---

## 2. §2 회신 — `*_anomaly` 타입: A 채택 (null 금지)

### 2.1 결정

**옵션 A 채택**: `if_anomaly`, `lof_anomaly`, `svm_anomaly` 모두 **항상 `boolean` 송신**. `null` 금지.

### 2.2 보장 메커니즘

#### 적재 시점

- `predictions/{cid}_{seg}_ml_predictions.csv`는 `phase7_ml_models.py` 산출물로, `if_anomaly/lof_anomaly/svm_anomaly` 컬럼은 **항상 boolean** (코드 확인: `labels == -1` 결과로 NaN 발생 불가).
- 신규 loader (`app/db/loader/phase7_ml.py`)에서 NaN 방지 코드 추가:
  ```python
  for col in ("if_anomaly", "lof_anomaly", "svm_anomaly"):
      df[col] = df[col].fillna(False).astype(bool)
  ```
- 예외 케이스(만일 NaN 발견 시): 해당 행을 적재 skip 후 WARN 로그 기록. 적재 후 DB에는 NaN 없음.

#### 응답 시점

- `MLSummary` 직렬화 시 `*_anomaly` 필드는 `bool` 타입 강제 (`bool(ml.if_anomaly) if ml else None` 패턴을 `bool(ml.if_anomaly) if ml else False`로 변경).
- `MLScore` 미존재 시(ml_scores 적재 누락 등) `*_anomaly`는 `false` 송신 (`null` 송신 금지).

### 2.3 합의안 §4.1 스키마 갱신

```jsonc
{
  "ml_vote":         number,            // 0~3
  "ml_detected":     boolean,
  "if_anomaly":      boolean,           // ← null 금지 (v2 정정)
  "if_score":        number  | null,
  "if_percentile":   number  | null,
  "lof_anomaly":     boolean,           // ← null 금지 (v2 정정)
  "lof_score":       number  | null,
  "lof_percentile":  number  | null,
  "svm_anomaly":     boolean,           // ← null 금지 (v2 정정)
  "svm_score":       number  | null,
  "svm_percentile":  number  | null
}
```

→ 프론트 측 `src/types/anomaly.ts:99-107`의 `boolean` 타입 유지 가능. 변경 불필요.

### 2.4 ORM 적재 정책

| 필드 | DB 컬럼 nullable | 적재 정책 |
|---|---|---|
| `ml_scores.if_anomaly` | nullable (기존 ORM) | **항상 NOT NULL 값 적재** (NaN → False) |
| `ml_scores.lof_anomaly` | nullable | 동일 |
| `ml_scores.svm_anomaly` | nullable | 동일 |
| `anomaly_results.if_anomaly` | nullable | 동일 (기존 `load_phase7.py` 로직 유지) |

→ DB 컬럼은 nullable 유지(스키마 마이그레이션 회피). 실제 값은 항상 boolean.

---

## 3. 합의안 기타 항목 — 프론트 v2 §3 수용 확인

프론트 v2 §3 표의 11개 합의 항목 모두 백엔드 측 변경 없이 그대로 진행.

추가 확인:
- §1.3 percentile 의미 라벨링 — A 채택 결과 "상위 N% 이상점" 표기 가능. 프론트 측 라벨 추가는 프론트 재량(백엔드 응답 변경 없음).
- §6 `frame_spec_frontend` 갱신 없음 재확인 — OK.

---

## 4. 최종 일정 (재확정)

| 단계 | 담당 | 산출 | 예상 |
|---|---|---|---|
| ① 본 회신 검토 + 합의 확정 | 양 팀 | 합의 완료 | 즉시 |
| ② `ml_scores` 적재 + percentile 산출 + batch flow 연결 + 명세 갱신 PR | 백엔드 | PR | 2일 |
| ⑤(부분) 프론트 통합 검증 — `*_score`, `*_percentile` 표시 | 프론트 | 회신 | 0.5일 |
| ③ `ml_projections` 적재 (PCA) + `/ml-map` 활성화 | 백엔드 | PR | 1일 |
| ⑤(완료) 프론트 통합 검증 — ML 결과맵 산점도 + highlight | 프론트 | 회신 | (위에 포함) |
| ④ 명세 갱신 PR (`api_spec_vN+1`, `db_schema_vN+1`) | 백엔드 | ②에 포함 또는 별도 PR | 병행 |

**병합 순서**: ② → ⑤(부분) → ③ → ⑤(완료) → ④(또는 ② 병행).

---

## 5. ② PR 작업 체크리스트 (백엔드 측)

본 PR에서 수행할 구체 작업:

- [ ] `app/db/loader/phase7_ml.py` 신설
  - [ ] `predictions/{cid}_{seg}_ml_predictions.csv` 로드
  - [ ] `*_anomaly` NaN → False 강제 (§2.2)
  - [ ] segment 내 `(1 - rank(pct=True)) * 100` percentile 산출 (3종, §1.3)
  - [ ] `ml_scores` INSERT — UNIQUE `(cid, seg, period)` 일치 확인
- [ ] `app/db/loader/phase7.py` 신설 — 루트 `load_phase7.py` 로직 이전
- [ ] `app/db/loader/runner.py` — `phase7`, `phase7_ml` loader 등록 (Phase 2~6 패턴)
- [ ] `app/services/batch.py` — Phase 6 → 7 → 7-ML → 적재 순서 추가
- [ ] `app/services/anomaly_panel.py:208~217` — `MLSummary` 직렬화에서 `*_anomaly` null → false 변경
- [ ] `load_phase7.py` 루트 스크립트 삭제 (이전 완료 후)
- [ ] `README.md` §배치 실행 흐름 갱신 (Phase 7/7-ml skip 표기 제거)
- [ ] `docs/db_schema_v6.md` § `ml_scores` — percentile 산출 정책 부록 추가 (§1.3 표 그대로)
- [ ] `docs/api_spec_v6.md` § `/anomalies/{id}/detail` — `ml_summary` 필드 타입 정정 (`*_anomaly: boolean`)
- [ ] 단위 테스트 — loader percentile 산출 결과 검증 (0~100 범위, anomaly 행이 상위 백분위)

---

## 6. ③ PR 작업 체크리스트 (이어서)

- [ ] `app/db/loader/phase7_ml.py` 확장 — `ml_projections` 적재
  - [ ] `features/{cid}_{seg}_features.csv` 로드 + `StandardScaler` 적용
  - [ ] `sklearn.decomposition.PCA(n_components=2, random_state=42)` 투영
  - [ ] `(cid, seg, period)` × 3 model_name (`isolation_forest`/`lof`/`ocsvm`) = 3 행 적재
  - [ ] 모델별 `anomaly_score`는 predictions 점수에서 매핑 (`if_score`/`lof_score`/`svm_score`)
  - [ ] `is_anomaly`도 predictions에서 매핑 (위 §2.2와 동일하게 boolean 보장)
  - [ ] `x_label="PC1"`, `y_label="PC2"` 고정
- [ ] `app/services/anomaly_panel.py:583~638` — `/ml-map` 빈 응답 fallback 제거 (실 데이터 응답)
- [ ] `is_highlight` 산출 — anomaly의 `period`와 일치하는 점 1개만 `true`
- [ ] `docs/db_schema_v6.md` § `ml_projections` — OI-15 해소 명기 (PCA 확정)
- [ ] `docs/api_spec_v6.md` § `/anomalies/{id}/ml-map` — `projection_method=pca`, `x_label/y_label` 고정 명기

---

## 7. 다음 단계

1. 프론트 측 본 회신에 추가 의견 없음 회신 → 합의 완결.
2. 백엔드 ② 착수 → PR 머지 시 프론트 알림.
3. 프론트 ⑤(부분) 검증 → 결과 회신.
4. 백엔드 ③ 착수 → PR 머지 시 프론트 알림.
5. 프론트 ⑤(완료) 검증 → 결과 회신.
6. 양 PR 머지 완료 후 본 협의 종결.

---

_v2 (2026-05-24) — 프론트엔드 v2 회신에 대한 백엔드 합의 최종안. LOF 산출식 정정 포함._
