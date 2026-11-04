"""Safe, descriptive download names for private doctor licence files."""

import unicodedata


def licence_filename(doctor_name: str, content_type: str) -> str:
    name = unicodedata.normalize("NFKC", doctor_name)
    name = "".join(char for char in name if char.isalnum() or char in " .-_' ")
    name = " ".join(name.split()).strip(". ")[:180].rstrip(". ") or "Doctor"
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[content_type]
    return f"{name} - licence.{extension}"
