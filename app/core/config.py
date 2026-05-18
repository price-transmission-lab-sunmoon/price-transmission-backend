from typing import Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    # 파이프라인 파라미터 (pipeline_output_spec_vN §파라미터 표, CFG-CORE-003)
    rolling_window: int = 48
    contamination: float = 0.10
    random_state: int = 42

    # 이상 탐지 임계값 (feature_spec_API-PANEL §4 — 하드코딩 금지)
    zscore_warning: float = 2.0   # Z-score 주의 임계값
    zscore_alert: float = 2.5     # Z-score 경보 임계값

    frame_version: str = "0.1.0"

    # doc1_technical_pipeline 현재 버전 (docs/docs_manifest.md §1 표와 일치해야 함)
    # 버전 갱신 시 manifest §1을 먼저 업데이트한 뒤 이 값을 변경한다.
    pipeline_spec_version: str = "v10"

    @field_validator("rolling_window")
    @classmethod
    def validate_rolling_window(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ROLLING_WINDOW은 양수여야 합니다.")
        return v

    @field_validator("contamination")
    @classmethod
    def validate_contamination(cls, v: float) -> float:
        if not 0 < v < 1:
            raise ValueError("CONTAMINATION은 0 초과 1 미만이어야 합니다.")
        return v


def get_settings() -> Settings:
    """설정 로딩 — 필수 변수 누락(CFG-CORE-001) vs 범위 위반(CFG-CORE-003) 분리."""
    try:
        return Settings()
    except ValidationError as e:
        error_types = [err["type"] for err in e.errors()]
        if any(t == "missing" for t in error_types):
            raise ConfigError(
                "CFG-CORE-001",
                "필수 환경 변수 누락 (DATABASE_URL, REDIS_URL 등)",
                {"missing_fields": [err["loc"] for err in e.errors() if err["type"] == "missing"]},
            ) from e
        raise ConfigError(
            "CFG-CORE-003",
            "파라미터 범위 위반 (ROLLING_WINDOW, CONTAMINATION 등)",
            {"errors": [{"field": err["loc"], "msg": err["msg"]} for err in e.errors()]},
        ) from e


settings = get_settings()
