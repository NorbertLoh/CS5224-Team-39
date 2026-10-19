from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "fulfilment"
    port: ServicePort = 8006
    cursor_secret: SecretStr | None = None
    dispensing_fixture_path: Path | None = None
    lalamove_api_key: SecretStr | None = None
    lalamove_api_secret: SecretStr | None = None
    delivery_locations_path: Path | None = None
    delivery_contacts_path: Path | None = None
    billing_url: str | None = None
    billing_secret: SecretStr | None = None
    payment_queue_name: str = Field(default="telelink-local-fulfilment", pattern=r"^[\w-]{1,80}$")

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.billing_url is not None:
            url = urlsplit(self.billing_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and self.environment not in {"local", "test"})
            ):
                raise ValueError("billing_url requires HTTPS outside local/test and no credentials")
            self.billing_url = self.billing_url.rstrip("/")
        if self.billing_secret is not None:
            if len(self.billing_secret.get_secret_value().encode()) < 32:
                raise ValueError("Billing secret requires at least 32 bytes")
            if self.cursor_secret == self.billing_secret:
                raise ValueError("Billing and cursor secrets must differ")
        for value, prefix in (
            (self.lalamove_api_key, "pk_test"),
            (self.lalamove_api_secret, "sk_test"),
        ):
            if value is not None and not value.get_secret_value().startswith(prefix):
                raise ValueError("Only Lalamove sandbox credentials are supported")
        if (self.lalamove_api_key is None) != (self.lalamove_api_secret is None):
            raise ValueError("Both Lalamove sandbox credentials are required")
        if self.dispensing_fixture_path is not None and self.environment not in {"local", "test"}:
            raise ValueError("Dispensing fixtures are restricted to local/test")
        if (
            self.cursor_secret is not None
            and len(self.cursor_secret.get_secret_value().encode()) < 32
        ):
            raise ValueError("Cursor secret requires at least 32 bytes")
        return self
