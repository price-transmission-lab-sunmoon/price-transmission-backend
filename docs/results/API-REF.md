# API-REF 구현 결과 — feat/be-api-reference

**feature_spec_API-REF_v4 §7 완료 기준 대조표**

| 기준 | 파일 | 상태 |
|------|------|------|
| GET /commodities 200 + 10개 품목 | app/api/v1/endpoints/commodities.py | 완료 |
| GET /commodities/{id} 200 + segment_meta | app/api/v1/endpoints/commodities.py | 완료 |
| GET /commodities/nonexistent 404 + COMMODITY_NOT_FOUND | app/services/reference.py | 완료 |
| GET /segments 200 + ETag + Cache-Control | app/api/v1/endpoints/meta.py | 완료 |
| GET /events 200 + ETag + Cache-Control | app/api/v1/endpoints/meta.py | 완료 |
| GET /freshness 200 + 날짜 3종 형식 | app/api/v1/endpoints/meta.py | 완료 |
| baselines Alembic 마이그레이션 | alembic/versions/0003_add_baselines.py | 완료 |
| cointegration_results Alembic 마이그레이션 | alembic/versions/0004_add_cointegration_results.py | 완료 |
| 참조 더미 픽스처 | tests/fixtures/reference_dummy.json | 완료 |
| 통합 테스트 (25개 케이스) | tests/test_api_reference.py | 완료 |

---

## 주요 설계 결정

- **segments 파생**: `route_type` 컬럼에서 런타임 파생 (`_route_type_to_segments()`). DB에 별도 저장 불필요.
- **has_anomaly_this_month / latest_anomaly_grade**: Phase 7 미구현 → 각각 `false` / `null` 하드코딩 (명세 §1.4).
- **warmup_end**: `baselines.warmup_end` 직접 반환. 별도 집계 불필요 (명세 D-06).
- **subperiod_id IS NULL**: 전체 기간 기준선 조회 조건 (명세 D-15). `subperiods` 테이블 FK는 `feat/pipeline-phase4-5`에서 추가.
- **ETag**: SHA-256 앞 32자, 첫 조회 시 계산 후 모듈 변수 캐시.

---

## 응답 샘플

### GET /api/v1/commodities (발췌)

```json
{
  "commodities": [
    {
      "commodity_id": "wheat",
      "name_kr": "밀",
      "name_en": "Wheat",
      "cluster": "grain",
      "has_wholesale": false,
      "route_type": "3seg",
      "segments": ["A", "B", "D_prime"],
      "analysis_start": "2000-01",
      "analysis_end": "2026-03",
      "has_anomaly_this_month": false,
      "latest_anomaly_grade": null
    }
  ]
}
```

### GET /api/v1/commodities/wheat (발췌)

```json
{
  "commodity_id": "wheat",
  "route_type": "3seg",
  "segments": ["A", "B", "D_prime"],
  "segment_meta": {
    "A": {
      "model_type": "VECM",
      "cointegrated": true,
      "normal_transmission_lag": 2,
      "transmission_elasticity": 0.72,
      "upstream_label": "국제가 (원화 환산)",
      "downstream_label": "수입단가",
      "warmup_end": "2003-12"
    }
  }
}
```

### GET /api/v1/commodities/nonexistent

```json
{
  "error": {
    "code": "COMMODITY_NOT_FOUND",
    "message": "요청한 품목을 찾을 수 없습니다.",
    "context": {"commodity_id": "nonexistent"}
  }
}
```

### GET /api/v1/freshness

```json
{
  "data_up_to": "2026-03",
  "next_run_date": "2026-04-15",
  "last_updated": "2026-04-01T03:00:00Z"
}
```

---

## 마이그레이션 체인

```
0001_initial_frame_tables (9개 Frame 테이블)
  └─ 0002_seed_reference_data (commodities/segments/events 시드)
       └─ 0003_add_baselines (baselines 테이블)
            └─ 0004_add_cointegration_results (cointegration_results 테이블)
```

⚠️ `0003` / `0004`는 `feat/be-api-reference` 임시 정의. 향후 파이프라인 브랜치 합류 시 중복 충돌 주의 (명세 §2 경고 참조).
