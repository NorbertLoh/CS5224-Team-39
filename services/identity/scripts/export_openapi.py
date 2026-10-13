"""Export service-local C01/C02 interface for consumers; no database connection."""

import json
from pathlib import Path

from app.main import create_app
from app.settings import Settings

if __name__ == "__main__":
    app = create_app(
        Settings(_env_file=None, root_path="/api/v1/identity", clinic_fixture_path=None)
    )
    schema = app.openapi()
    schema["servers"] = [{"url": "/api/v1/identity"}]
    destination = Path(__file__).resolve().parents[1] / "docs/openapi.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
