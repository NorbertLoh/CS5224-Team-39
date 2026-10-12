"""Validated configuration from SERVICE_* environment variables or local .env."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVICE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    name: str = Field(default="template", pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    environment: Literal["local", "test", "development", "demo", "production"] = "local"
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    docs_enabled: bool | None = None
    root_path: str = ""

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
