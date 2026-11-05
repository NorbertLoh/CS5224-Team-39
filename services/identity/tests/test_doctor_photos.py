from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image, PngImagePlugin
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError
from test_api import (
    TENANT_A,
    TENANT_KEY,
    api,
    api_database,
    headers,
    path,
    signing_key,
    tenant_token,
)
from test_doctor_applications import apply, assign, review

from app.services.doctor_photos import sanitize_photo

__all__ = ["api", "api_database", "signing_key"]


def picture(format="PNG", size=(640, 480)):
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "Private camera metadata")
    Image.new("RGB", size, "teal").save(output, format=format, pnginfo=metadata)
    return output.getvalue()


def upload(api, actor="doctor", content=None, content_type="image/png"):
    return api.client.put(
        "/me/doctor-profile/photo",
        content=picture() if content is None else content,
        headers=headers(api, actor) | {"Content-Type": content_type},
    )


def photo_path(profile):
    return f"/doctors/{profile['doctor_id']}/photos/{profile['photo_id']}"


@pytest.mark.parametrize("format,media_type", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_photo_decodes_resizes_and_strips_metadata(format, media_type):
    clean = sanitize_photo(picture(format), media_type)
    with Image.open(BytesIO(clean)) as image:
        assert image.format == "JPEG" and image.size == (512, 384)
        assert not image.getexif() and "Comment" not in image.info
    assert b"Private camera metadata" not in clean


@pytest.mark.parametrize(
    "content,media_type",
    [
        (b"\x89PNG\r\n\x1a\ninvalid", "image/png"),
        (b"<svg></svg>", "image/png"),
        (picture(), "image/jpeg"),
        (picture(size=(4097, 1)), "image/png"),
        (picture()[:40], "image/png"),
    ],
)
def test_invalid_photos_are_rejected(api, content, media_type):
    assert upload(api, content=content, content_type=media_type).status_code == 422
    assert (
        api.client.get("/me/doctor-profile", headers=headers(api, "doctor")).json()["photo_id"]
        is None
    )


def test_photo_lifecycle_directory_and_public_read(api):
    own = headers(api, "doctor")
    empty = api.client.get("/me/doctor-profile", headers=own)
    assert empty.status_code == 200 and empty.json()["photo_id"] is None
    first = upload(api)
    assert first.status_code == 200
    profile = first.json()
    public = api.client.get(photo_path(profile))
    assert public.status_code == 200 and public.headers["content-type"] == "image/jpeg"
    assert public.headers["cache-control"] == "no-store"
    assert public.headers["x-content-type-options"] == "nosniff"
    assert api.client.get("/me/doctor-profile", headers=own).json() == profile
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    directory = api.client.get(
        f"/internal/clinics/{TENANT_A}/doctors",
        headers={"Authorization": "Bearer " + tenant_token(aud="telelink-identity-doctors")},
    ).json()
    assert directory["items"][0]["photo_id"] == profile["photo_id"]
    assert upload(api, content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413
    assert api.client.get(photo_path(profile)).status_code == 200
    second = upload(api, content=picture("JPEG"), content_type="image/jpeg").json()
    assert second["photo_id"] != profile["photo_id"]
    assert api.client.get(photo_path(profile)).status_code == 404
    assert api.client.get(photo_path(second)).status_code == 200
    assert api.client.get(f"/doctors/{uuid4()}/photos/{second['photo_id']}").status_code == 404
    assert api.client.delete("/me/doctor-profile/photo", headers=own).status_code == 204
    assert api.client.delete("/me/doctor-profile/photo", headers=own).status_code == 204
    assert api.client.get(photo_path(second)).status_code == 404
    assert api.client.get("/me/doctor-profile", headers=own).json()["photo_id"] is None


@pytest.mark.parametrize("actor", ["patient", "admin_a", "platform", "former", "target"])
def test_only_active_approved_doctors_manage_own_photo(api, actor):
    assert upload(api, actor=actor).status_code == 403
    assert api.client.get("/me/doctor-profile", headers=headers(api, actor)).status_code == 403
    assert (
        api.client.delete("/me/doctor-profile/photo", headers=headers(api, actor)).status_code
        == 403
    )


def test_authentication_and_private_document_separation(api):
    assert api.client.put("/me/doctor-profile/photo", content=picture()).status_code == 401
    assert api.client.get("/me/doctor-profile").status_code == 401
    assert api.client.delete("/me/doctor-profile/photo").status_code == 401
    assert upload(api, content_type="application/pdf").status_code == 422
    profile = upload(api).json()
    assert (
        api.client.put(
            f"/doctors/{profile['doctor_id']}/photos/{profile['photo_id']}",
            content=picture(),
            headers=headers(api, "patient"),
        ).status_code
        == 405
    )
    document = api.client.post(
        "/me/doctor-documents",
        content=b"%PDF-private",
        headers=headers(api, "doctor") | {"Content-Type": "application/pdf"},
    ).json()
    assert (
        api.client.get(
            f"/doctors/{profile['doctor_id']}/photos/{document['document_id']}"
        ).status_code
        == 404
    )
    assert api.client.get(f"/doctor-documents/{document['document_id']}").status_code == 401


def test_membership_and_verification_revocation_hide_public_photo(api):
    assign(api)
    apply(api)
    assert review(api).status_code == 200
    profile = upload(api, actor="target").json()
    assert api.client.get(photo_path(profile)).status_code == 200
    assert review(api, decision="revoked").status_code == 200
    assert api.client.get(photo_path(profile)).status_code == 404
    other = upload(api).json()
    api.client.delete(path(subject=api.ids["doctor"]), headers=headers(api, "platform"))
    assert api.client.get(photo_path(other)).status_code == 404


def test_migration_preserves_stored_photo(api):
    profile = upload(api).json()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(DBAPIError, match="Stored doctor photos prevent downgrade"):
        command.downgrade(config, "0006")
    assert api.client.get(photo_path(profile)).status_code == 200
    api.client.delete("/me/doctor-profile/photo", headers=headers(api, "doctor"))
    command.downgrade(config, "0006")
    command.upgrade(config, "head")
    assert (
        api.client.get("/me/doctor-profile", headers=headers(api, "doctor")).json()["photo_id"]
        is None
    )
