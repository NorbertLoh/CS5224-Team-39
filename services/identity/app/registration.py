"""Self-registration from a verified Cognito account, with patient access only."""

from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from telelink_common.auth import bearer
from telelink_common.errors import DomainError

from app.api import DB, User, me
from app.database import find_subject
from app.models import Subject
from app.schemas import IdentityRead

router = APIRouter(tags=["registration"])


def account_attributes(settings, access_token, subject):
    # Endpoint comes exclusively from trusted service configuration, never the client.
    issuer = urlsplit(settings.auth_issuer)
    endpoint = settings.aws_endpoint_url or f"{issuer.scheme}://{issuer.netloc}"
    try:
        response = httpx.post(
            endpoint,
            json={"AccessToken": access_token},
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.GetUser",
            },
            timeout=5,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Account lookup failed")
        items = response.json()["UserAttributes"]
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("Name"), str)
            or not isinstance(item.get("Value"), str)
            for item in items
        ):
            raise ValueError("Invalid account attributes")
        attributes = {item["Name"]: item["Value"] for item in items}
        if attributes.get("sub") != subject or attributes.get("email_verified") != "true":
            raise DomainError(
                403, "verified_email_required", "Verify your email before continuing."
            )
        email = attributes.get("email", "").strip().lower()
        name = attributes.get("name", "").strip()
        if not email or "@" not in email or len(email) > 320 or len(name) > 200:
            raise ValueError("Invalid account attributes")
        return email, name or email
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise DomainError(
            503,
            "account_lookup_unavailable",
            "Unable to verify account details. Try signing in again.",
        ) from None


@router.post("/me/registration", response_model=IdentityRead)
def register_patient(
    request: Request,
    principal: User,
    session: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if find_subject(session, principal.subject) is not None:
        return me(principal, session)
    email, name = account_attributes(
        request.app.state.settings, credentials.credentials, principal.subject
    )
    try:
        session.execute(
            insert(Subject)
            .values(
                cognito_sub=principal.subject,
                email=email,
                display_name=name,
                global_roles=["patient"],
            )
            .on_conflict_do_nothing(index_elements=[Subject.cognito_sub])
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        # Never attach a new Cognito sub to an existing identity by email.
        raise DomainError(
            409, "email_already_registered", "This email is already linked to an account."
        ) from None
    return me(principal, session)
