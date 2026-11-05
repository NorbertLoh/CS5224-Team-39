"""Decode bounded portraits and discard metadata before public display."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from telelink_common.errors import DomainError

MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_TYPES = {"image/png": "PNG", "image/jpeg": "JPEG"}


def sanitize_photo(content: bytes, content_type: str) -> bytes:
    try:
        with Image.open(BytesIO(content), formats=["PNG", "JPEG"]) as image:
            if (
                image.format != PHOTO_TYPES.get(content_type)
                or image.width > 4096
                or image.height > 4096
                or image.width * image.height > 16_000_000
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError("Unsupported photo")
            image.load()
            portrait = ImageOps.exif_transpose(image).convert("RGB")
            portrait.thumbnail((512, 512), Image.Resampling.LANCZOS)
            # Copy pixels into a new image so EXIF, comments and other metadata are omitted.
            clean = Image.new("RGB", portrait.size)
            clean.paste(portrait)
            output = BytesIO()
            clean.save(output, format="JPEG", quality=85)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise DomainError(
            422, "invalid_photo", "Upload a valid PNG or JPEG, up to 4096 pixels per side (16 MP)."
        ) from None
