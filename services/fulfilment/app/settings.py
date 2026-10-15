from pathlib import Path

from pydantic import SecretStr, model_validator
from telelink_common.settings import ServiceName, ServicePort, ServiceSettings


class Settings(ServiceSettings):
    name: ServiceName = "fulfilment"
    port: ServicePort = 8006
    cursor_secret: SecretStr | None = None
    dispensing_fixture_path: Path | None = None

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.dispensing_fixture_path is not None and self.environment not in {"local", "test"}:
            raise ValueError("Dispensing fixtures are restricted to local/test")
        if (
            self.cursor_secret is not None
            and len(self.cursor_secret.get_secret_value().encode()) < 32
        ):
            raise ValueError("Cursor secret requires at least 32 bytes")
        return self
