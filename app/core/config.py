from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_host: str = Field(default="127.0.0.1", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    database_url: str = Field(default="sqlite:///./causalstream.db", alias="DATABASE_URL")
    ai_service_url: str = Field(default="http://127.0.0.1:8001", alias="AI_SERVICE_URL")
    ai_service_timeout_seconds: float = Field(default=10, alias="AI_SERVICE_TIMEOUT_SECONDS")
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ALLOWED_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_frame_size_mb: int = Field(default=5, alias="MAX_FRAME_SIZE_MB")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
