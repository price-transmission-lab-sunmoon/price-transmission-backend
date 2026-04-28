from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Literal
from app.core.exceptions import ConfigError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 필수 환경 변수 (CFG-CORE-001)
    database_url: str
    redis_url: str

    # 선택 환경 변수
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_allowed_origins: str = "http://localhost:5173"

    # 파이프라인 파라미터 (pipeline_output_spec_v5 §파라미터 표, CFG-CORE-003)
    rolling_window: int = 48
    contamination: float = 0.10
    random_state: int = 42

    frame_version: str = "0.1.0"

    @field_validator("rolling_window")
    @classmethod
    def validate_rolling_window(cls, v: int) -> int:
        if v <= 0:
            raise ConfigError("CFG-CORE-003", "ROLLING_WINDOW은 양수여야 합니다.", {"value": v})
        return v

    @field_validator("contamination")
    @classmethod
    def validate_contamination(cls, v: float) -> float:
        if not 0 < v < 1:
            raise ConfigError("CFG-CORE-003", "CONTAMINATION은 0~1 사이여야 합니다.", {"value": v})
        return v


def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as e:
        raise ConfigError(
            "CFG-CORE-001",
            f"필수 환경 변수 누락 또는 설정 오류: {e}",
            {"error": str(e)},
        ) from e


settings = get_settings()
