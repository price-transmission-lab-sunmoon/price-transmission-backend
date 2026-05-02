"""에러 응답 envelope — api_spec_vN §공통 사항 + exception_spec_vN §부록 A."""
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    context: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
