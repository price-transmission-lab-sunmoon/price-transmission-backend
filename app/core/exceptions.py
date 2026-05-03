"""예외 클래스 계층 + 에러 체이닝 — exception_spec_vN §부록 A + exception_design_vN §2 구현."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")


# ── 예외 클래스 계층 (exception_spec_vN §부록 A) ────────────────────────────

class ProjectError(Exception):
    def __init__(self, code: str, message: str, context: dict | None = None):
        self.code = code
        self.message = message
        self.context = context or {}
        super().__init__(f"[{code}] {message}")


class DBError(ProjectError):
    def __init__(self, code: str, message: str, context: dict | None = None, table: str | None = None):
        super().__init__(code, message, context)
        self.table = table


class APIError(ProjectError):
    def __init__(
        self,
        code: str,
        message: str,
        context: dict | None = None,
        http_status: int = 500,
        public_code: str = "INTERNAL_ERROR",
    ):
        super().__init__(code, message, context)
        self.http_status = http_status
        self.public_code = public_code


class PipelineError(ProjectError):
    """파이프라인 단계 예외 (PL-*). phase 속성으로 어느 Phase에서 발생했는지 식별.

    feat/pipeline-phase* 브랜치에서 실제 파이프라인 코드가 추가될 때 사용한다.
    """
    def __init__(self, code: str, message: str, context: dict | None = None, phase: str = ""):
        super().__init__(code, message, context)
        self.phase = phase


class ParseError(ProjectError):
    """DB→API 또는 API→FE 경계에서 발생하는 파싱 예외 (PARSE-*)."""
    def __init__(self, code: str, message: str, context: dict | None = None, boundary: str = ""):
        super().__init__(code, message, context)
        self.boundary = boundary


class ConfigError(ProjectError):
    """설정·환경 변수 예외 (CFG-*). FATAL — 부팅 중단."""
    pass


class ExternalAPIError(ProjectError):
    """외부 API 호출 예외 (EXT-*)."""
    def __init__(
        self,
        code: str,
        message: str,
        context: dict | None = None,
        source: str = "",
        retry_count: int = 0,
    ):
        super().__init__(code, message, context)
        self.source = source
        self.retry_count = retry_count


# ── 에러 체이닝 (exception_design_vN §2) ────────────────────────────────────

def _format_chain(chain: list[Exception]) -> str:
    """예외 체인을 ORIGIN → 현재 순으로 포맷팅 (exception_design_vN §2.2)."""
    lines: list[str] = []
    for i, exc in enumerate(chain):
        if isinstance(exc, ProjectError):
            code = exc.code
            msg = exc.message
            snapshot = ""
            if i == 0 and exc.context:  # ORIGIN에만 context 출력
                items = ", ".join(f"{k}={v!r}" for k, v in exc.context.items())
                snapshot = f" | context: {{{items}}}"
            prefix = "ORIGIN" if i == 0 else "      "
            arrow = "  " if i == 0 else " └─ "
            lines.append(f"{prefix}{arrow}[{code}] {msg}{snapshot}")
        else:
            prefix = "ORIGIN" if i == 0 else "      "
            lines.append(f"{prefix}  [{type(exc).__name__}] {exc!s}")
    return "\n".join(lines)


def trace_error_chain(exc: Exception) -> dict:
    """예외 체인을 역추적하여 ORIGIN·전파 경로·포맷 문자열 반환 (exception_design_vN §2.2).

    Returns:
        {
            "origin": Exception,       # 최초 발생 예외
            "chain": list[Exception],  # ORIGIN → 현재 순서
            "formatted": str,          # 로그 출력용 문자열
        }
    """
    chain: list[Exception] = []
    current: Exception | None = exc
    while current is not None:
        chain.append(current)
        current = current.__cause__
    chain.reverse()  # ORIGIN이 첫 번째
    return {
        "origin": chain[0],
        "chain": chain,
        "formatted": _format_chain(chain),
    }


# ── 응답 헬퍼 ────────────────────────────────────────────────────────────────

def _error_body(code: str, message: str, context: dict | None = None) -> dict:
    body: dict = {"code": code, "message": message}
    if context:
        body["context"] = context
    return {"error": body}


# ── 전역 예외 핸들러 (exception_design_vN §2.4 + frame_spec_vN §8.4) ────────────

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """APIError → http_status / public_code 반환."""
    result = trace_error_chain(exc)
    logger.error(
        result["formatted"],
        extra={"error_code": result["origin"].code if isinstance(result["origin"], ProjectError) else "UNKNOWN",
               "context": result["origin"].context if isinstance(result["origin"], ProjectError) else {}},
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=_error_body(exc.public_code, exc.message),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic 검증 실패 → 400 / API-VAL-001."""
    errors = exc.errors()
    ctx = {
        "loc": str(errors[0].get("loc")) if errors else "",
        "input": str(errors[0].get("input")) if errors else "",
    }
    logger.warning(
        "Pydantic 검증 실패",
        extra={"error_code": "API-VAL-001", "context": ctx},
    )
    return JSONResponse(
        status_code=400,
        content=_error_body("API-VAL-001", "요청 파라미터 검증 실패", ctx),
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """DBError / PipelineError / ParseError / ExternalAPIError / 기타 → 500 / INTERNAL_ERROR.

    ORIGIN 코드를 보존하여 로깅하고 사용자에게는 INTERNAL_ERROR만 노출
    (exception_spec_vN §4 API-INT-001, exception_design_vN §2.4).
    """
    result = trace_error_chain(exc)
    origin = result["origin"]

    if isinstance(origin, ProjectError):
        extra_ctx = dict(origin.context)
        if isinstance(origin, PipelineError) and origin.phase:
            extra_ctx["phase"] = origin.phase
        logger.error(
            result["formatted"],
            extra={"error_code": origin.code, "context": extra_ctx},
        )
    else:
        logger.exception(
            result["formatted"],
            extra={"error_code": "API-INT-001", "context": {"exc_type": type(exc).__name__}},
        )
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."),
    )
