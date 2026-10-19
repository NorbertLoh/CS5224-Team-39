from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServiceSettings


class Settings(ServiceSettings):
    notification_secret: SecretStr | None = None
    name: ServiceName = "document"
    port: int = Field(default=8007, ge=1, le=65535)
    scheduling_url: str | None = None
    cursor_secret: SecretStr | None = None
    s3_browser_endpoint_url: str | None = None
    download_ttl_seconds: int = Field(default=120, ge=30, le=300)
    records_url: str | None = None
    records_secret: SecretStr | None = None
    document_bucket: str = Field(default="telelink-local-documents", min_length=3, max_length=63)
    document_queue_name: str = Field(default="telelink-local-document", pattern=r"^[\w-]{1,80}$")
    records_timeout_seconds: float = Field(default=5, ge=0.1, le=30)

    @model_validator(mode="after")
    def validate_worker_configuration(self):
        if self.notification_secret:
            value = self.notification_secret.get_secret_value()
            if len(value.encode()) < 32 or any(
                key and key.get_secret_value() == value
                for key in (self.records_secret, self.cursor_secret)
            ):
                raise ValueError("Notification secret needs distinct 32+ bytes")
        if self.cursor_secret:
            value = self.cursor_secret.get_secret_value()
            if len(value.encode()) < 32:
                raise ValueError("cursor_secret requires at least 32 bytes")
            if self.records_secret and value == self.records_secret.get_secret_value():
                raise ValueError("Cursor and records secrets must differ")
        if self.scheduling_url:
            url = urlsplit(self.scheduling_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("scheduling_url requires HTTPS outside local/test")
            self.scheduling_url = self.scheduling_url.rstrip("/")
        if self.s3_browser_endpoint_url:
            url = urlsplit(self.s3_browser_endpoint_url)
            if (
                self.environment not in {"local", "test"}
                or not self.aws_endpoint_url
                or url.scheme not in {"http", "https"}
                or url.hostname not in {"localhost", "127.0.0.1"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise ValueError("s3_browser_endpoint_url requires a local browser emulator host")
            self.s3_browser_endpoint_url = self.s3_browser_endpoint_url.rstrip("/")
        if self.records_url:
            url = urlsplit(self.records_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("records_url requires HTTPS outside local/test and no credentials")
            self.records_url = self.records_url.rstrip("/")
        if self.records_secret and len(self.records_secret.get_secret_value().encode()) < 32:
            raise ValueError("records_secret requires at least 32 bytes")
        return self
