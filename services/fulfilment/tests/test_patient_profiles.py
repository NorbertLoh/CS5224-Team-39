from uuid import uuid4

import httpx
import jwt
import pytest

from app.patient_profiles import HttpPatientProfiles, PatientContactUnavailable
from app.settings import Settings

SECRET = "patient-profile-lookup-secret-32-bytes-minimum"
PATIENT = uuid4()


def test_profile_lookup_uses_service_auth_and_matching_patient():
    def handler(request):
        assert request.url.path == f"/internal/patients/{PATIENT}/delivery-contact"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SECRET,
            algorithms=["HS256"],
            audience="telelink-identity-delivery",
            issuer="telelink-service:fulfilment",
        )
        assert claims["sub"] == "fulfilment"
        return httpx.Response(
            200,
            json={"patient_id": str(PATIENT), "name": "Synthetic patient", "phone": "+6581234567"},
        )

    source = HttpPatientProfiles(
        Settings(
            _env_file=None,
            environment="test",
            identity_url="http://identity.test",
            profile_secret=SECRET,
        ),
        transport=httpx.MockTransport(handler),
    )
    assert source.get_contact(PATIENT) == {"name": "Synthetic patient", "phone": "+6581234567"}
    source.close()


@pytest.mark.parametrize(
    "status,data",
    [
        (404, {}),
        (503, {}),
        (200, {}),
        (200, {"patient_id": str(uuid4()), "name": "Other patient", "phone": "+6581234567"}),
    ],
)
def test_recipient_lookup_fails_closed(status, data):
    source = HttpPatientProfiles(
        Settings(
            _env_file=None,
            environment="test",
            identity_url="http://identity.test",
            profile_secret=SECRET,
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=data)),
    )
    with pytest.raises(PatientContactUnavailable):
        source.get_contact(PATIENT)
    source.close()
