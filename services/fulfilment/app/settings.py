from pathlib import Path

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "fulfilment"
    port: ServicePort = 8006
    cursor_secret: SecretStr | None = None
    dispensing_fixture_path: Path | None = None
    lalamove_api_key: SecretStr | None = None
    lalamove_api_secret: SecretStr | None = None
    delivery_locations_path: Path | None = None

    @model_validator(mode="after")
    def validate_configuration(self):
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
