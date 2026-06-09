from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "emby-soso"
    app_port: int = 8080
    log_level: str = "info"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+psycopg://emby:emby@localhost:5432/emby_soso",
        description="SQLAlchemy database URL (PostgreSQL or MySQL)",
    )

    redis_url: str | None = None
    redis_enabled: Literal["auto", "true", "false"] = "auto"

    scheduler_enabled: bool = True

    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_language: str = "zh-CN"
    tmdb_image_base_url: str = "https://image.tmdb.org/t/p"

    data_source_root: str = "/data/source"
    data_library_root: str = "/data/library"

    static_dir: str = "/app/static"

    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = "admin"
    auth_secret_key: str = Field(
        default="change-me-use-a-long-random-string-in-production",
        description="JWT signing secret",
    )
    auth_token_expire_hours: int = Field(default=168, ge=1, le=8760)
    auth_cookie_name: str = "emby_soso_token"
    auth_cookie_secure: bool = False

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://") and "+psycopg" not in value:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("mysql://"):
            return value.replace("mysql://", "mysql+pymysql://", 1)
        return value

    @property
    def is_mysql(self) -> bool:
        return self.database_url.startswith("mysql")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def redis_active(self) -> bool:
        if self.redis_enabled == "false":
            return False
        if self.redis_enabled == "true":
            return bool(self.redis_url)
        return bool(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
