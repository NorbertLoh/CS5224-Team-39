from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import get_session
from app.main import create_app
from app.settings import Settings


def test_only_successful_public_reads_opt_in_to_shared_caching():
    clinic = SimpleNamespace(
        tenant_id=uuid4(),
        slug="public-clinic",
        name="Public clinic",
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        primary_color="#112233",
        logo_url=None,
        description="Public description",
        consultation_price_minor=1000,
        currency="SGD",
    )
    database = SimpleNamespace(
        scalar=lambda _: clinic,
        scalars=lambda _: SimpleNamespace(all=lambda: [clinic]),
    )
    app = create_app(Settings(_env_file=None, cursor_secret="c" * 32))
    app.dependency_overrides[get_session] = lambda: database
    with TestClient(app) as client:
        listing = client.get("/clinics")
        anonymous = client.get("/clinics/by-slug/public-clinic")
        signed_in = client.get(
            "/clinics/by-slug/public-clinic",
            headers={"Authorization": "Bearer ignored-public-token"},
        )
        assert listing.status_code == anonymous.status_code == signed_in.status_code == 200
        assert anonymous.json() == signed_in.json()
        for response in (listing, anonymous, signed_in):
            assert (
                response.headers["Cache-Control"]
                == "public, max-age=0, s-maxage=60, must-revalidate"
            )
        # Validation failures, missing resources and private/write paths never opt in.
        assert client.get("/clinics?limit=0").headers["Cache-Control"] == "no-store"
        database.scalar = lambda _: None
        missing = client.get("/clinics/by-slug/missing")
        assert missing.status_code == 404 and missing.headers["Cache-Control"] == "no-store"
        for response in (
            client.get(f"/clinics/{clinic.tenant_id}"),
            client.post("/clinics", json={}),
        ):
            assert response.status_code >= 400
            assert response.headers["Cache-Control"] == "no-store"
