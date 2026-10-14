"""Event validation errors that name fields but never echo payload values."""

from pydantic import ValidationError


class EventValidationError(ValueError):
    """A malformed, unsupported or misrouted event; never acknowledge it as success."""


def safe_error(prefix: str, error: ValidationError) -> EventValidationError:
    problems = ", ".join(
        ".".join(str(part) for part in item["loc"]) + f" ({item['type']})"
        for item in error.errors()
    )
    return EventValidationError(f"{prefix}: {problems}")
