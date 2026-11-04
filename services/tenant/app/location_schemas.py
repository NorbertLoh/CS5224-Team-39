"""Shared pickup validation for registration and Clinic Settings."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: str = Field(pattern=r"^1\.\d{1,7}$")
    lng: str = Field(pattern=r"^10[34]\.\d{1,7}$")

    @field_validator("lat", "lng")
    @classmethod
    def singapore(cls, value, info):
        lower, upper = (
            (Decimal("1.1"), Decimal("1.5"))
            if info.field_name == "lat"
            else (Decimal("103.5"), Decimal("104.1"))
        )
        if not lower <= Decimal(value) <= upper:
            raise ValueError("Choose a location within Singapore")
        return value


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_line: str = Field(min_length=1, max_length=300)
    postal_code: str = Field(pattern=r"^\d{6}$")
    country_code: Literal["SG"] = "SG"
    coordinates: Coordinates
    pickup_contact: "PickupContact | None" = None

    @field_validator("address_line")
    @classmethod
    def plain_address(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a plain address without control characters")
        return value


class PickupContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    phone: str = Field(pattern=r"^\+65[689][0-9]{7}$")

    @field_validator("name")
    @classmethod
    def contact_name(cls, value):
        if not value.strip():
            raise ValueError("Enter a pickup contact name")
        return value.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def singapore_phone(cls, value):
        if isinstance(value, str):
            value = value.translate(str.maketrans("", "", " -()"))
            if len(value) == 8:
                value = "+65" + value
        return value


class RegistrationLocation(Location):
    pickup_contact: PickupContact
