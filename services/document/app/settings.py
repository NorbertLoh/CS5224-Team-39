from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "document"
    records_url: str | None = None
    records_secret: SecretStr | None = None
    document_bucket: str = Field(default="telelink-local-documents", min_length=3, max_length=63)
    document_queue_name: str = Field(default="telelink-local-document", pattern=r"^[\w-]{1,80}$")
    records_timeout_seconds: float = Field(default=5, ge=0.1, le=30)

    @model_validator(mode="after")
    def validate_worker_configuration(self):
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
