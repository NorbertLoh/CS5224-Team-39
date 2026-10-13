"""Validated configuration from SERVICE_* environment variables or local .env."""

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ServiceName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
ServicePort = Annotated[int, Field(ge=1, le=65535)]


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    name: ServiceName = "template"
    environment: Literal["local", "test", "development", "demo", "production"] = "local"
    host: str = Field(default="127.0.0.1", min_length=1)
    port: ServicePort = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    docs_enabled: bool | None = None
    root_path: str = ""
    database_url: SecretStr | None = None
    database_timeout_seconds: int = Field(default=3, ge=1, le=30)
    auth_issuer: str | None = None
    auth_jwks_url: str | None = None
    auth_client_id: str | None = Field(default=None, min_length=1)
    auth_required_scopes: str = ""
    identity_url: str | None = None
    identity_timeout_seconds: int = Field(default=3, ge=1, le=30)

    @field_validator("identity_url")
    @classmethod
    def validate_identity_url(cls, value, info):
        if value is None:
            return value
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and info.data.get("environment") not in {"local", "test"})
        ):
            raise ValueError(
                "identity_url requires HTTP(S), HTTPS outside local/test, and no credentials/query"
            )
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_auth(self):
        values = (self.auth_issuer, self.auth_jwks_url, self.auth_client_id)
        if not any(values):
            return self
        if not all(values):
            raise ValueError("auth_issuer, auth_jwks_url and auth_client_id are required together")
        for value in (self.auth_issuer, self.auth_jwks_url):
            url = urlsplit(value)
            if url.username or url.password or url.query or url.fragment:
                raise ValueError(
                    "authentication URLs cannot contain credentials, query or fragment"
                )
            if url.scheme not in {"http", "https"} or not url.hostname:
                raise ValueError("authentication URLs must be absolute HTTP(S) URLs")
        if self.environment in {"local", "test"}:
            return self
        aws_issuer = re.fullmatch(
            r"https://cognito-idp\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/[A-Za-z0-9_-]+",
            self.auth_issuer,
        )
        expected_jwks = self.auth_issuer + "/.well-known/jwks.json"
        if not aws_issuer or self.auth_jwks_url != expected_jwks:
            raise ValueError("non-local environments require an AWS Cognito issuer and its JWKS")
        return self

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
