"""DB에서 API 경계까지 사용하는 공통 타입, 날짜 변환 헬퍼.

stream.py / raw_prices.py / scatter.py / anomaly_panel.py 에 중복 정의돼 있던
_safe_float / _safe_period / _parse_yyyymm / _f / _period_str 를 단일 출처로 통합.

두 가지 float 변환 계약을 의도적으로 분리한다:
  - safe_float: 엄격. 오버플로우 시 PARSE-NUM-001 발생 (불량 데이터 노출)
  - to_float:   관대. 실패 시 None (요약/패널 직렬화용)
"""
from __future__ import annotations

import re
from datetime import date

from app.core.exceptions import APIError, ParseError


def safe_float(value: object, table: str, column: str) -> float | None:
    """Decimal 또는 None을 float으로 변환. 오버플로우 시 PARSE-NUM-001."""
    if value is None:
        return None
    try:
        return float(value)
    except (OverflowError, ValueError) as e:
        raise ParseError(
            "PARSE-NUM-001",
            "NUMERIC을 float으로 변환 중 오버플로우",
            context={"table": table, "column": column, "value": str(value)},
            boundary="DB에서 API 경계",
        ) from e


def safe_period(value: date | None, table: str, column: str) -> str:
    """date를 YYYY-MM으로 변환. None 또는 변환 실패 시 PARSE-DATE-001."""
    if value is None:
        raise ParseError(
            "PARSE-DATE-001",
            "DATE를 YYYY-MM으로 변환 실패: 값이 NULL",
            context={"table": table, "column": column, "raw_value": None},
            boundary="DB에서 API 경계",
        )
    try:
        return value.strftime("%Y-%m")
    except Exception as e:
        raise ParseError(
            "PARSE-DATE-001",
            "DATE를 YYYY-MM으로 변환 실패",
            context={"table": table, "column": column, "raw_value": str(value)},
            boundary="DB에서 API 경계",
        ) from e


def parse_yyyymm(
    value: str,
    field: str,
    *,
    code: str,
    public_code: str = "INVALID_DATE_RANGE",
) -> date:
    """YYYY-MM을 date(y, m, 1)로 변환. 형식 오류 시 APIError(code) 400.

    code: 호출 도메인별 내부 코드 (스트림=API-STR-002, 패널=API-MET-001).
    """
    m = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not m:
        raise APIError(
            code,
            f"날짜 형식이 올바르지 않습니다: {value!r}",
            context={"field": field, "value": value},
            http_status=400,
            public_code=public_code,
        )
    y, mo = int(m.group(1)), int(m.group(2))
    if mo < 1 or mo > 12:
        raise APIError(
            code,
            f"날짜 형식이 올바르지 않습니다: {value!r}",
            context={"field": field, "value": value},
            http_status=400,
            public_code=public_code,
        )
    return date(y, mo, 1)


def to_float(v: object) -> float | None:
    """관대한 float 변환. 실패 시 None (예외 없음)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def period_str(d: date | None) -> str:
    """date를 YYYY-MM으로 변환. None이면 빈 문자열 반환 (예외 없음)."""
    if d is None:
        return ""
    return d.strftime("%Y-%m")
