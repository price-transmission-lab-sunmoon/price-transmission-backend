from typing import Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 필수 환경 변수
    database_url: str
    redis_url: str

    # 선택 환경 변수
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_allowed_origins: str = "http://localhost:5173"

    # 파이프라인 파라미터
    rolling_window: int = 48
    contamination: float = 0.10
    contamination_range: list[float] = [0.05, 0.10, 0.15]
    random_state: int = 42

    # 이상 탐지 임계값
    zscore_warning: float = 2.0   # Z-score 주의 임계값
    zscore_alert: float = 2.5     # Z-score 경보 임계값

    frame_version: str = "0.1.0"

    # 파이프라인 문서 버전. manifest와 일치 유지
    pipeline_spec_version: str = "v10"

    # Redis 캐싱 파라미터
    redis_ttl: int = 3600               # TODO: 환경별 TTL 분리 검토
    redis_cache_prefix: str = "pricelens"  # 캐시 키 프리픽스 (환경 격리)

    # 배치 스케줄 파라미터
    # TODO: 배치 실행 파라미터를 환경변수로 완전 외부화 검토
    batch_schedule_day: int = 15       # 매월 실행일
    batch_schedule_hour: int = 3       # 실행 시각 (KST)
    batch_schedule_tz: str = "Asia/Seoul"   # 배치 타임존
    batch_misfire_grace_sec: int = 3600    # APScheduler misfire grace time (초)

    # DB 파이프라인 적재 파라미터
    pipeline_data_root: str = "data/processed"
    db_pool_size: int = 10

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

    @field_validator("zscore_warning", "zscore_alert")
    @classmethod
    def validate_zscore(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ZSCORE 임계값은 양수여야 합니다.")
        return v


def get_settings() -> Settings:
    """설정 로딩. 필수 변수 누락 또는 범위 위반 시 유형별 ConfigError 분리."""
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
