"""이상 탐지 요약 집계 서비스 — feature_spec_API-ANO_v7 §1.3·§6 기준.

더미 단계: 고정값 반환 (frame_spec_backend_vN §8.1).
실제 연동 전환 조건: feat/phase7-stat dev 머지 완료 후 anomaly_results 실 데이터 적재 확인 시점.
"""
from __future__ import annotations

from app.core.exceptions import APIError
from app.schemas.anomaly import AnomalySummaryResponse

_VALID_GRADES = {"high", "medium", "reference"}


def parse_grades(grade_str: str) -> list[str]:
    """콤마 구분 grade 문자열을 파싱하고 허용 값 검증.

    feature_spec_API-ANO_v7 §2 — 허용 값: high, medium, reference.
    허용 값 외 입력 시 API-VAL-001 (400) 발생.
    """
    grades = [g.strip() for g in grade_str.split(",") if g.strip()]
    invalid = [g for g in grades if g not in _VALID_GRADES]
    if not grades or invalid:
        raise APIError(
            code="API-VAL-001",
            message=f"허용되지 않는 grade 값: {invalid or '(빈 값)'}",
            context={"grade": grade_str, "allowed": sorted(_VALID_GRADES)},
            http_status=400,
            public_code="API-VAL-001",
        )
    return grades


async def get_anomaly_summary(
    month: str | None,
    grade_str: str,
) -> AnomalySummaryResponse:
    """이상 탐지 요약 집계.

    더미 단계: grade 파싱·검증 후 고정값 반환.
    feat/phase7-stat 완료 후 anomaly_results 실 DB 조회로 전환.
    """
    try:
        parse_grades(grade_str)  # 검증만 수행; 더미 단계에서 필터로 사용하지 않음

        # 더미 단계 고정값 (feature_spec_API-ANO_v7 §6, frame_spec_backend_vN §8.1)
        return AnomalySummaryResponse(
            reference_month="2026-03",
            total_count=0,
            prev_month_count=0,
            count_diff=0,
            anomalies=[],
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(
            code="API-INT-001",
            message="이상 요약 집계 중 DB 오류",
            context={"month": month, "grades": grade_str},
            http_status=500,
            public_code="INTERNAL_ERROR",
        ) from e
