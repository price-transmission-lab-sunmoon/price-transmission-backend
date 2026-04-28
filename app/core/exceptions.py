"""예외 클래스 계층 — exception_spec_v2 §부록 A 직접 구현."""
from __future__ import annotations
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


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


class ParseError(ProjectError):
    def __init__(self, code: str, message: str, context: dict | None = None, boundary: str = ""):
        super().__init__(code, message, context)
        self.boundary = boundary


class ConfigError(ProjectError):
    pass


class ExternalAPIError(ProjectError):
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


# ── 전역 예외 핸들러 ──────────────────────────────────────────────────────────

def _error_body(code: str, message: str, context: dict | None = None) -> dict:
    body: dict = {"code": code, "message": message}
    if context:
        body["context"] = context
    return {"error": body}


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    import logging
    logger = logging.getLogger("app")
    logger.error(
        exc.message,
        extra={"error_code": exc.code, "context": exc.context},
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=_error_body(exc.public_code, exc.message),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    import logging
    logger = logging.getLogger("app")
    ctx = {"loc": str(exc.errors()[0].get("loc")), "input": str(exc.errors()[0].get("input"))}
    logger.warning("Pydantic 검증 실패", extra={"error_code": "API-VAL-001", "context": ctx})
    return JSONResponse(
        status_code=400,
        content=_error_body("API-VAL-001", "요청 파라미터 검증 실패", ctx),
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging
    logger = logging.getLogger("app")
    logger.exception(
        f"내부 미매핑 예외: {exc}",
        extra={"error_code": "API-INT-001", "context": {"exc_type": type(exc).__name__}},
    )
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."),
    )
