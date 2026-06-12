"""에러 응답 envelope."""
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    context: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
