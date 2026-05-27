# 백엔드 → 프론트엔드 회신 v3 — Phase 7-ML 회귀 #1·#2 핫픽스

**작성일**: 2026-05-24
**작성자**: 백엔드 (바게스타니 샤킬라)
**대상**: 프론트엔드 (하대수)
**참조**:
- `docs/backend_reply_phase7ml_v2.md` (백엔드 합의안)
- 프론트엔드 검증 회신 (2026-05-24, "회귀 2건")
**상태**: 핫픽스 머지 / 재검증 대기

---

## 0. 결론 요약

| 회귀 | 원인 | 수정 |
|---|---|---|
| #1 `*_percentile` 전부 NULL | `load_pipeline_outputs.py` (수동 적재 스크립트)가 predictions CSV에서 `if_percentile` 컬럼을 직접 읽으려 했으나 **CSV에 percentile 컬럼이 없음** → NULL 적재 | `load_ml_scores`에 segment 단위 `rank(pct=True, ascending=False) * 100` 산출 블록 추가 |
| #2 `/ml-map` 전부 `total_points=0` | `load_pipeline_outputs.py`에 `ml_projections` 적재 함수 자체 없음 | `load_ml_projections` 함수 신규 추가 (StandardScaler + PCA(n=2), `(cid, seg, period) × 3 model` = 3행) |

→ **합의안 자체 위반 없음**. `app/db/loader/phase7_ml.py`(② / ③ PR 본체)는 정상 구현되어 있으나, 사용자가 batch 트리거 대신 **수동 스크립트(`load_pipeline_outputs.py`)** 를 사용했고, 해당 스크립트가 신규 정책 미반영 상태였다.

---

## 1. 원인 상세

### 1.1 백엔드 코드 흐름 (현재)

```
[방법 A] 배치 (월간 자동 / POST /admin/batch/trigger)
  → app/services/batch.py → app/db/loader/phase7_ml.py::load_phase7_ml()
  → percentile 산출 ✔, ml_projections 적재 ✔ (② / ③ PR 본체)

[방법 B] 수동 적재 (개발 환경에서 사용)
  → python load_pipeline_outputs.py
  → percentile 산출 ✘ (predictions CSV에 컬럼 없음), ml_projections 적재 ✘ (함수 없음)
```

프론트 검증 환경은 방법 B로 적재되어 있어 회귀 발생.

### 1.2 회귀 #1 — percentile NULL

`load_pipeline_outputs.py` (수정 전):
```python
F(r.get("if_percentile")),    # predictions CSV에 컬럼 없음 → None
F(r.get("lof_percentile")),   # 동일
F(r.get("svm_percentile")),   # 동일
```

predictions CSV 컬럼 정의 (`pipeline/preprocessing/Phase7/phase7_ml_models.py:141~152`):
```
date, if_anomaly, if_score, lof_anomaly, lof_score, svm_anomaly, svm_score,
ml_consensus_count, ml_detected
```

→ percentile은 산출되지 않는다. 회신 v2 §1 합의안의 핵심이 "**백엔드 적재 시점에 산출**"이었던 이유.

### 1.3 회귀 #2 — ml_projections 미적재

`load_pipeline_outputs.py`에 `load_ml_projections` 함수 자체가 없었다. `app/db/loader/phase7_ml.py`(③ PR)에는 정상 구현되어 있으나, 수동 스크립트는 ml_scores만 적재.

---

## 2. 핫픽스 — `load_pipeline_outputs.py` 수정

### 2.1 회귀 #1 수정 (`load_ml_scores` 갱신)

`app/db/loader/phase7_ml.py`의 `_compute_percentiles` 로직과 동일하게 산출 블록 추가.

```python
# 전 predictions 통합 후 segment 단위 percentile 산출
df = pd.concat([...], ignore_index=True)
grp = df.groupby(["commodity_id", "segment_id"])
for src, dst in (
    ("if_score", "if_percentile"),
    ("lof_score", "lof_percentile"),
    ("svm_score", "svm_percentile"),
):
    df[dst] = grp[src].rank(pct=True, ascending=False) * 100
```

추가로 `BF` helper 신설 — `*_anomaly` NaN → False 강제 (회신 v2 §2.2 일관).

### 2.2 회귀 #2 수정 (`load_ml_projections` 신규 함수)

```python
async def load_ml_projections(conn, run_id):
    """features CSV → StandardScaler → PCA(n=2) → ml_projections."""
    for (cid, seg), grp in features_df.groupby(["commodity_id", "segment_id"]):
        X_valid = grp[_PCA_FEATURE_COLS].dropna()
        if len(X_valid) < 2:
            continue
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_valid)
        pca = PCA(n_components=2, random_state=42)
        XY = pca.fit_transform(X_scaled)
        ...
```

적재 구조: `(cid, seg, period)` × 3 `model_name` (`isolation_forest`/`lof`/`ocsvm`) = 3행. 좌표 동일, `anomaly_score`/`is_anomaly`는 predictions에서 매핑. `x_label="PC1"`, `y_label="PC2"`, `projection_method="pca"` 고정.

`main()`에서 `load_ml_scores` 직후 호출 추가.

---

## 3. 재현 / 검증 절차

### 3.1 백엔드 측 재적재

```powershell
cd C:\...\price-transmission-backend
python load_pipeline_outputs.py
```

기대 출력:
```
[Phase 7-ML]
  ml_scores: N행 (M개 파일) + percentile 산출
  ml_projections: 3N행 (N 관측치 × 3 model)
```

### 3.2 회귀 #1 재검증

```powershell
Invoke-RestMethod "http://localhost:8001/api/v1/anomalies/6786/detail" |
  Select-Object -ExpandProperty ml_summary
```

기대 응답 (percentile 채워짐):
```jsonc
{
  "if_anomaly": true,  "if_score": -0.5416,  "if_percentile": 97.3,
  "lof_anomaly": true, "lof_score": -2.9738, "lof_percentile": 98.1,
  "svm_anomaly": true, "svm_score": -3.5e-05, "svm_percentile": 95.7
}
```

### 3.3 회귀 #2 재검증

```powershell
foreach ($m in @("isolation_forest","lof","ocsvm")) {
  Invoke-RestMethod "http://localhost:8001/api/v1/anomalies/6786/ml-map?model=$m&projection_method=pca" |
    Select-Object model, total_points, @{N='first_point';E={$_.points[0]}}
}
```

기대: `total_points > 0` (segment 내 유효 관측치 수 만큼), `points[].x_value/y_value` finite.

---

## 4. 합의안 자체 점검 (재확인)

| 합의안 항목 | 상태 |
|---|---|
| §1 percentile 옵션 A (백엔드 산출) | ✔ 코드 적용. 핫픽스로 수동 스크립트까지 일관 |
| §1 LOF 산출식 (3종 동일 반전) | ✔ 코드 적용 |
| §2 `*_anomaly` boolean 강제 | ✔ 코드 적용. `BF` helper로 수동 스크립트까지 일관 |
| §3 일정 | ✔ 핫픽스 추가 (시간 추정 1시간 미만) |
| §4.1 MLSummary 11 필드 불변 | ✔ |
| §6 ③ ml_projections PCA | ✔ 코드 적용. 핫픽스로 수동 스크립트까지 일관 |

`app/db/loader/phase7_ml.py`(② / ③ PR 본체)의 정합성에는 변동이 없다.

---

## 5. 후속 개선 안 (선택)

향후 코드 중복 해소를 위해 다음 중 하나 검토 가능:

| 옵션 | 장단점 |
|---|---|
| 현행 유지 | `app/db/loader/phase7_ml.py`(SQLAlchemy async) + `load_pipeline_outputs.py`(asyncpg) 별개 유지. 단순. 변경 시 양쪽 동기 필요. |
| 통합 | 수동 스크립트가 `app/db/loader/*`를 호출하도록 리팩터. 코드 중복 0. 의존성 복잡. |
| 폐기 | `load_pipeline_outputs.py` 삭제 후 `python -m app.db.loader.run_manual` 같은 CLI 단일화. |

본 PR 범위는 핫픽스에 한정. 통합/폐기는 별도 협의.

---

## 6. 요청 사항

1. `load_pipeline_outputs.py` 핫픽스 머지 후 백엔드 측 재적재 1회 수행 (`python load_pipeline_outputs.py`).
2. §3.2 / §3.3 재현 명령으로 회귀 #1·#2 해소 확인 후 프론트 통합 검증 ⑤ 진행.
3. 검증 결과 별도 회신 부탁드립니다 (본 doc v4로 갱신).

---

_v3 (2026-05-24) — 회귀 #1·#2 핫픽스. 합의안 자체 변동 없음._
