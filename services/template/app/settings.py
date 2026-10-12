"""Validated configuration from SERVICE_* environment variables or local .env."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVICE_", env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )

    name: str = Field(default="template", pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    environment: Literal["local", "test", "development", "demo", "production"] = "local"
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    docs_enabled: bool | None = None
    root_path: str = ""
    database_url: SecretStr | None = None
    database_timeout_seconds: int = Field(default=3, ge=1, le=30)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
        except Exception:
            raise ValueError("database_url must be a valid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg" or not url.database:
            raise ValueError("database_url requires postgresql+psycopg and a database name")
        return value

    @field_validator("root_path")
    @classmethod
    def validate_root_path(cls, value: str) -> str:
        if value and (not value.startswith("/") or "?" in value or "#" in value):
            raise ValueError(
                "root_path must be empty or an absolute URL path without query/fragment"
            )
        return value.rstrip("/")

    @property
    def expose_docs(self) -> bool:
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.environment != "production"
