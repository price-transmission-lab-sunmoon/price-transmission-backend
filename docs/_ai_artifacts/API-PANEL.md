# 결과 명세 — API-PANEL (분석 수치 패널 엔드포인트)

**기능 번호**: API-PANEL  
**브랜치**: `feature/API-PANEL`  
**참조 명세**: `feature_spec_API-PANEL_v6.md`  
**작성일**: 2026-05-18  
**작성자**: Claude Code (담당: 바게스타니 샤킬라)

---

## 1. 구현 완료 항목 (feature_spec §7 완료 기준 기준)

| 완료 기준 항목 | 상태 | 비고 |
|---|---|---|
| 5개 엔드포인트 서비스 레이어 실 구현 | ✅ | `app/services/anomaly_panel.py` 신규 |
| `api_spec_vN §패널 엔드포인트` 응답 필드명·타입 1:1 구현 | ✅ | schemas 3방향 일치 확인 |
| 예외 코드 10종 구현 (`exception_spec_v6` 기준) | ✅ | §3 예외처리 목록 참조 |
| §4 파라미터 전체 `settings.py` 참조 (하드코딩 0건) | ✅ | `ZSCORE_WARNING`, `ZSCORE_ALERT`, `ROLLING_WINDOW`, `RANDOM_STATE`, `CONTAMINATION` |
| ORM 모델 4종 추가 (`baselines`, `irf_data`, `ml_scores`, `ml_projections`) | ✅ | `app/db/models/anomaly.py` 수정 |
| `docs/results/API-PANEL.md` 작성 | ✅ | 본 파일 |

### 실 DB 연동 전제 조건 (미충족 — 선행 브랜치 대기 중)

| 항목 | 상태 | 선행 브랜치 |
|---|---|---|
| `anomaly_results` 실데이터 적재 | 대기 | `feat/phase7-stat` |
| `ml_scores`, `ml_projections` 실데이터 적재 | 대기 | `feat/phase7-ml` |
| `irf_data`, `baselines`, `subperiods`, `breakpoints` 적재 | 대기 | `feat/be-db-pipeline` |

---

## 2. 구현 파일 목록

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `app/services/anomaly_panel.py` | **신규** | 패널 5개 엔드포인트 비즈니스 로직 (다중 테이블 조인·judgment_path 생성) |
| `app/api/v1/endpoints/anomalies.py` | 수정 | Frame 더미 → 서비스 레이어 실 호출로 교체. `get_db` 의존성 주입 추가 |
| `app/db/models/anomaly.py` | 수정 | ORM 추가: `Subperiod`, `Breakpoint`, `Baseline`, `IRFData`, `CointegrationResult`, `MLScore`, `MLProjection` (7종) |
| `app/core/config.py` | 수정 | `zscore_warning: float = 2.0`, `zscore_alert: float = 2.5` 추가 |
| `app/schemas/anomaly.py` | 수정 | `StatMetrics.zscore_threshold_warning/alert` 하드코딩 제거 → 서비스 레이어 주입 |

---

## 3. 예외처리 구현 목록 (feature_spec §5.1 — 10종)

| 예외 코드 | HTTP | public_code | 발생 위치 |
|---|---|---|---|
| `API-ANO-001` | 404 | `ANOMALY_NOT_FOUND` | `_fetch_anomaly()` — anomaly_id 미존재 |
| `API-ANO-002` | 500 | `PIPELINE_DATA_MISSING` | `_fetch_stat_ts()` — stat_timeseries 행 누락 |
| `API-ANO-003` | 404 | `ML_MAP_NOT_READY` | `get_ml_map()` — ml_projections 미산출 |
| `API-MET-001` | 400 | `INVALID_METRIC` | `get_stat_series()` — 허용 외 metric |
| `API-MET-002` | 400 | `SNAPSHOT_METRIC_ON_SERIES` | `get_stat_series()` — iqr·asymmetry 요청 |
| `API-MET-003` | 400 | `INVALID_METRIC` | FastAPI Literal 검증 → API-VAL-001 경로 |
| `API-STR-002` | 400 | `INVALID_DATE_RANGE` | `get_stat_series()` — from > to |
| `API-VAL-001` | 400 | — | FastAPI `RequestValidationError` 핸들러 |
| `API-SEG-001` | 400 | `INVALID_SEGMENT` | segments 테이블 조인 실패 시 (현재 None 반환 후 처리) |
| `API-INT-001` | 500 | `INTERNAL_ERROR` | 모든 엔드포인트 — 미매핑 내부 예외 catch-all |

---

## 4. 필드명 3방향 일치 확인

`db_schema_v5` ↔ `api_spec_v5` ↔ `app/schemas/anomaly.py` 주요 필드 매핑:

| DB 컬럼 | API 필드 | Schema 필드 | 비고 |
|---|---|---|---|
| `baselines.normal_transmission_lag` | `stat_metrics.normal_lag` | `StatMetrics.normal_lag` | 컬럼명→필드명 변환 (서비스 레이어) |
| `anomaly_results.zscore_value` | (미노출) | — | D-03: 수치는 `stat_timeseries.zscore` 참조 |
| `breakpoints.bp_dates` | `stat_metrics.bp_dates` | `StatMetrics.bp_dates` | D-16: `baselines.bp_dates`가 아닌 `breakpoints.bp_dates` |
| `stat_timeseries.ect_or_spread` | `stat_metrics.ect_or_spread` | `StatMetrics.ect_or_spread` | metric="ect" 파라미터와 컬럼명 다름 (서비스 매핑) |
| `asymmetry_results.model_type` | `stat_snapshot.model_type` | `StatSnapshotAsymmetryResponse.model_type` | `protected_namespaces=()` 설정 필요 |
| `irf_data.irf_peak_horizon` | `irfs[].peak_horizon` | `IRFCurve.peak_horizon` | horizon=0 행에서만 읽음 |
| `ml_projections.model_name` | `model` 파라미터 | `MLMapResponse.model` | 파라미터 → 쿼리 조건 매핑 |

---

## 5. 설계 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `judgment_path` 생성 위치 | 백엔드 서비스 (`_build_judgment_path()`) | D-04: 파이프라인·프론트가 아닌 백엔드 생성 원칙 |
| `baselines` 조인 조건 | `subperiod_id IS NULL` | D-15: 전체 기간 기준선만 API 노출 |
| `breakpoints` 출처 | `breakpoints.bp_dates` | D-16: `baselines.bp_dates`는 오기, 수정 반영 |
| `ml_scores` 조인 키 | `(commodity_id, segment_id, period)` | DB FK 없음 — 직접 조인 (feature_spec §2) |
| `is_highlight` 생성 | `period == anomaly.period` 비교 | `ml_projections`에 컬럼 없음 — 서비스 파생 |
| `up_samples`/`down_samples` | `stat_timeseries.upstream_pct` 부호로 구분 | DB 컬럼 없음 — 서비스 집계 |
| `zscore_threshold_*` | `settings.zscore_warning/alert` 주입 | feature_spec §4 하드코딩 금지 |
| OI-15 (`projection_method`) | `pca` 기본값 고정, `feature_direct` 허용 파라미터로 노출 | OI-15 미확정 — S4 내 결정 예정 |

---

## 6. 미구현·보류 사항

| 항목 | 이유 | 담당 브랜치 |
|---|---|---|
| Redis 캐싱 | `feat/be-redis` 담당 범위 | `feat/be-redis` |
| `judgment_path` 최종 문구 | D-04 PM 리뷰 후 반영 | PM 최수안 승인 후 패치 |
| OI-15 `projection_method` 확정 | S4 내 별도 결정 | S4 스프린트 |
| 실 DB 200 OK 확인 | `feat/phase7-ml` 미완료 | `feat/phase7-ml` → 이후 테스트 |

---

## 7. PR 체크리스트 (feature_spec §10 기준)

- [x] 5개 엔드포인트 서비스 레이어 구현 완료
- [x] 예외 코드 10종 구현 (`exception_spec_v6` §5.1 기준)
- [x] §4 파라미터 `settings.py` 참조 확인 (하드코딩 0건)
- [x] `db_schema_v5` ↔ `api_spec_v5` ↔ `schemas` 필드명 불일치 0건
- [x] ORM 모델 7종 추가 (`app/db/models/anomaly.py`)
- [ ] 실 DB 데이터 기반 200 OK 확인 (wheat·banana) — `feat/phase7-ml` 완료 후
- [ ] 에러 케이스 10종 실 테스트 케이스 통과 — 선행 데이터 적재 후
- [ ] PM 승인 (feature_spec §9)

---

*Redis 캐싱 미포함 — `feat/be-redis` 브랜치에서 추가 예정.*  
*breakpoints D-16 수정 반영: `breakpoints.bp_dates` 컬럼 사용.*  
*baselines D-15 반영: `subperiod_id IS NULL` 조건 적용.*
