"""Ephemeral node leases and room ownership; session locks serialize assignment changes."""

import hashlib
import secrets
from datetime import timedelta
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from telelink_common.errors import DomainError

from app.models import RoomAssignment, SignallingNode


def clock(db):
    # Wall clock after lock acquisition, not PostgreSQL transaction start time.
    return db.scalar(select(func.clock_timestamp()))


def unavailable():
    raise DomainError(
        503, "signalling_unavailable", "No signalling server is available. Retry shortly."
    )


def denied():
    raise DomainError(403, "signalling_denied", "Signalling ownership is no longer valid.")


def endpoint(value, settings):
    """Only registered literal addresses in explicitly allowed networks; no DNS/SSRF."""
    try:
        url = urlsplit(value)
        address = ip_address(url.hostname)
        port = url.port or 80
        if (
            url.scheme != "http"
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or port != settings.signalling_internal_port
            or address.version != 4
            or not any(address in ip_network(n) for n in settings.signalling_networks)
        ):
            denied()
    except (ValueError, TypeError):
        denied()
    return f"http://{address}:{port}"


def heartbeat(db, settings, body):
    if not settings.signalling_matchmaker:
        denied()
    internal_url = endpoint(body.internal_url, settings)
    token_digest = hashlib.sha256(body.node_token.encode()).hexdigest()
    db.execute(
        insert(SignallingNode)
        .values(
            node_id=body.node_id,
            token_digest=token_digest,
            internal_url=internal_url,
            draining=body.draining,
            lease_expires_at=clock(db) + timedelta(seconds=settings.signalling_lease_seconds),
        )
        .on_conflict_do_nothing(index_elements=["node_id"])
    )
    node = db.scalar(
        select(SignallingNode)
        .where(SignallingNode.node_id == body.node_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    instant = clock(db)
    if (
        not secrets.compare_digest(node.token_digest, token_digest)
        or node.internal_url != internal_url
        or node.lease_expires_at <= instant
    ):
        denied()
    node.draining = node.draining or body.draining
    node.lease_expires_at = instant + timedelta(seconds=settings.signalling_lease_seconds)
    db.flush()
    return {
        "lease_expires_at": node.lease_expires_at,
        "lease_seconds": settings.signalling_lease_seconds,
    }


def healthy(db, node):
    return node is not None and node.lease_expires_at > clock(db)


def assign(db, record):
    """Caller holds the consultation session lock before touching its assignment."""
    assignment = db.get(RoomAssignment, record.session_id, populate_existing=True)
    if assignment and healthy(
        db, db.get(SignallingNode, assignment.node_id, populate_existing=True)
    ):
        return assignment  # A draining node keeps its existing rooms.
    node = db.scalar(
        select(SignallingNode)
        .where(
            SignallingNode.lease_expires_at > func.clock_timestamp(),
            SignallingNode.draining.is_(False),
        )
        .order_by(
            select(func.count())
            .select_from(RoomAssignment)
            .where(RoomAssignment.node_id == SignallingNode.node_id)
            .correlate(SignallingNode)
            .scalar_subquery(),
            SignallingNode.node_id,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if node is None or not healthy(db, node):
        unavailable()
    if assignment is None:
        assignment = RoomAssignment(session_id=record.session_id, node_id=node.node_id, version=1)
        db.add(assignment)
    else:
        assignment.node_id = node.node_id
        assignment.version += 1
    db.flush()
    return assignment


def validate_assignment(db, settings, record, lease):
    if lease.node_id is None:
        if settings.signalling_matchmaker:
            denied()
        return
    node = db.get(SignallingNode, lease.node_id, populate_existing=True)
    assignment = db.get(RoomAssignment, record.session_id, populate_existing=True)
    if (
        not healthy(db, node)
        or assignment is None
        or assignment.node_id != lease.node_id
        or assignment.version != lease.assignment_version
    ):
        denied()
    return node


def validate(db, settings, record, lease, node_id=None, node_token=None):
    node = validate_assignment(db, settings, record, lease)
    if node is None:
        if node_id is not None:
            denied()
        return
    if (
        node_id != lease.node_id
        or not node_token
        or not secrets.compare_digest(
            node.token_digest, hashlib.sha256(node_token.encode()).hexdigest()
        )
    ):
        denied()


def resolve(db, settings, node_id):
    if not settings.signalling_matchmaker:
        denied()
    node = db.get(SignallingNode, node_id, populate_existing=True)
    if not healthy(db, node):
        unavailable()
    return {"internal_url": endpoint(node.internal_url, settings)}
