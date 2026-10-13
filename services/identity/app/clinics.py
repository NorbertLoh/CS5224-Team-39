"""Explicitly local C02/F14 clinic adapter; A08/A10 supply live integration."""

import json
from pathlib import Path
from uuid import UUID

from telelink_common.errors import DomainError


class ClinicDirectory:
    def __init__(self, fixture_path: Path | None):
        self.tenant_ids = None
        if fixture_path is not None:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            if data.get("fixture_kind") != "synthetic_shared_dataset":
                raise ValueError("clinic_fixture_path requires the agreed F14 dataset")
            self.tenant_ids = {UUID(clinic["tenant_id"]) for clinic in data["clinics"]}

    def require_clinic(self, tenant_id: UUID):
        if self.tenant_ids is None:
            raise DomainError(503, "unavailable", "Clinic validation is not configured.")
        if tenant_id not in self.tenant_ids:
            raise DomainError(404, "not_found", "Resource not found.")
