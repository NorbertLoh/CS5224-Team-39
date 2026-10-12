"""Check shared synthetic fixture shapes and cross-service relationships (stdlib only)."""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID


class InvalidFixture(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidFixture(message)


def instant(value):
    require(
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value),
        f"Invalid UTC timestamp: {value!r}",
    )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def money(value):
    require(
        isinstance(value, dict) and set(value) == {"amount_minor", "currency"},
        f"Invalid money shape: {value!r}",
    )
    require(
        type(value["amount_minor"]) is int
        and 0 <= value["amount_minor"] <= 9007199254740991
        and value["currency"] == "SGD",
        f"Invalid SGD money: {value!r}",
    )
    return value["amount_minor"]


# Required fields from C02-C04. Additive response fields remain permitted under C01.
FIELDS = {
    "subjects": "subject_id cognito_sub display_name global_roles",
    "clinics": (
        "tenant_id slug name status branding consultation_price commission_bps "
        "review_reason created_at updated_at"
    ),
    "memberships": "membership_id subject_id tenant_id roles status created_at updated_at",
    "slots": "slot_id tenant_id doctor_id starts_at ends_at availability consultation_price",
    "appointments": (
        "appointment_id tenant_id patient_id doctor_id slot_id status starts_at "
        "ends_at hold_expires_at consultation_price payment_id payment_resolution "
        "created_at updated_at"
    ),
    "payments": (
        "payment_id tenant_id patient_id purpose appointment_id order_id quote_id "
        "status amount commission_bps commission_amount clinic_amount resolution "
        "created_at updated_at"
    ),
    "catalogue": "medication_id tenant_id display_name unit_label unit_price active updated_at",
    "notes": "note_id tenant_id appointment_id patient_id doctor_id text created_at updated_at",
    "prescriptions": (
        "prescription_id tenant_id appointment_id patient_id doctor_id status "
        "items issued_at created_at updated_at"
    ),
    "orders": (
        "order_id tenant_id prescription_id appointment_id patient_id status "
        "medicine_status payment_status payment_id quote_id delivery_id items "
        "medication_subtotal delivery_fee total created_at updated_at"
    ),
    "quotes": (
        "quote_id order_id tenant_id status medication_subtotal delivery_fee "
        "total expires_at created_at"
    ),
    "documents": (
        "document_id tenant_id appointment_id prescription_id kind status created_at updated_at"
    ),
    "deliveries": "delivery_id order_id tenant_id status created_at updated_at",
}
KEYS = dict(
    zip(
        FIELDS,
        [
            "subject_id",
            "tenant_id",
            "membership_id",
            "slot_id",
            "appointment_id",
            "payment_id",
            "medication_id",
            "note_id",
            "prescription_id",
            "order_id",
            "quote_id",
            "document_id",
            "delivery_id",
        ],
    )
)
ENUMS = {
    "clinics": {"status": "pending_review active rejected suspended"},
    "memberships": {"status": "active revoked"},
    "slots": {"availability": "available unavailable"},
    "appointments": {
        "status": "held pending_payment confirmed in_progress completed expired cancelled no_show",
        "payment_resolution": "none awaiting_payment confirmed refund_required refunded",
    },
    "payments": {
        "status": "pending succeeded failed refund_pending refunded refund_failed",
        "purpose": "consultation medication_delivery",
        "resolution": "none refund_required",
    },
    "prescriptions": {"status": "draft issued voided"},
    "orders": {
        "status": "awaiting_payment paid submitting dispatched delivered cancelled exception",
        "medicine_status": "not_ready ready",
        "payment_status": "unpaid pending succeeded refund_required refunded",
    },
    "quotes": {"status": "active accepted expired superseded"},
    "documents": {"kind": "prescription_pdf", "status": "pending ready failed"},
    "deliveries": {"status": "pending submitted picked_up delivered cancelled failed unknown"},
}


def validate(data):
    require(
        data.get("fixture_kind") == "synthetic_shared_dataset"
        and type(data.get("schema_version")) is int
        and data["schema_version"] == 1,
        "Expected synthetic shared dataset version 1",
    )
    now = instant(data["as_of"])
    index = {}
    all_ids = set()

    def walk(value, key=""):
        if isinstance(value, dict):
            if "amount_minor" in value:
                money(value)
            for name, child in value.items():
                walk(child, name)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif value is not None:
            if key.endswith("_id"):
                require(
                    isinstance(value, str) and str(UUID(value)) == value, f"Invalid {key}: {value}"
                )
            if key.endswith("_at") or key == "as_of":
                instant(value)

    walk(data)
    for collection, fields in FIELDS.items():
        require(
            isinstance(data.get(collection), list) and data[collection], f"Missing {collection}"
        )
        index[collection] = {}
        for row in data[collection]:
            require(set(fields.split()) <= row.keys(), f"Missing required fields in {collection}")
            ident = row[KEYS[collection]]
            require(isinstance(ident, str), f"Null or invalid primary ID in {collection}")
            require(ident not in all_ids, f"Duplicate resource ID: {ident}")
            all_ids.add(ident)
            index[collection][ident] = row
            for field, values in ENUMS.get(collection, {}).items():
                require(row[field] in values.split(), f"Invalid {collection}.{field}: {row[field]}")
            if "created_at" in row:
                require(instant(row["created_at"]) <= now, f"Future creation: {ident}")
            if "updated_at" in row:
                require(
                    instant(row.get("created_at", row["updated_at"]))
                    <= instant(row["updated_at"])
                    <= now,
                    f"Invalid update chronology: {ident}",
                )

    def get(collection, ident):
        require(ident in index[collection], f"Missing {collection} reference: {ident}")
        return index[collection][ident]

    def same(left, right, fields):
        for field in fields.split():
            require(left[field] == right[field], f"Mismatched {field}: {left} vs {right}")

    def member(subject, tenant, role):
        return any(
            m["subject_id"] == subject
            and m["tenant_id"] == tenant
            and m["status"] == "active"
            and role in m["roles"]
            for m in data["memberships"]
        )

    require(len(data["clinics"]) == 2, "F14 requires two clinics")
    require(len({c["slug"] for c in data["clinics"]}) == 2, "Duplicate clinic slugs")
    require(
        len({s["cognito_sub"] for s in data["subjects"]}) == len(data["subjects"]),
        "Duplicate subjects",
    )
    for s in data["subjects"]:
        require(
            s["cognito_sub"].startswith("synthetic-"),
            "Runtime Cognito subjects must not be committed",
        )
        require(set(s["global_roles"]) <= {"patient", "platform_admin"}, "Invalid global role")
    pairs = set()
    for m in data["memberships"]:
        get("subjects", m["subject_id"])
        get("clinics", m["tenant_id"])
        pair = (m["subject_id"], m["tenant_id"])
        require(pair not in pairs, "Duplicate subject/clinic membership")
        pairs.add(pair)
        require(
            m["roles"]
            and len(m["roles"]) == len(set(m["roles"]))
            and set(m["roles"]) <= {"doctor", "clinic_admin"},
            "Invalid membership roles",
        )
    for c in data["clinics"]:
        require(
            any(member(s["subject_id"], c["tenant_id"], "clinic_admin") for s in data["subjects"]),
            "Clinic missing active administrator",
        )
        require(
            type(c["commission_bps"]) is int and 0 <= c["commission_bps"] <= 10000,
            "Invalid commission",
        )
        require(
            set(c["branding"]) == {"primary_color", "logo_url", "description"}
            and re.fullmatch(r"#[0-9A-Fa-f]{6}", c["branding"]["primary_color"]),
            "Invalid branding",
        )

    occupied = Counter()
    reserved_states = {
        "held",
        "pending_payment",
        "confirmed",
        "in_progress",
        "completed",
        "no_show",
    }
    for a in data["appointments"]:
        s = get("slots", a["slot_id"])
        same(a, s, "tenant_id doctor_id starts_at ends_at")
        require(
            "patient" in get("subjects", a["patient_id"])["global_roles"],
            "Appointment patient lacks role",
        )
        if a["status"] in {"held", "pending_payment", "confirmed", "in_progress"}:
            require(
                member(a["doctor_id"], a["tenant_id"], "doctor"),
                "Live appointment doctor lacks membership",
            )
        if a["status"] in reserved_states:
            occupied[a["slot_id"]] += 1
        if a["status"] in {"held", "pending_payment", "expired"}:
            deadline = instant(a["hold_expires_at"])
            require(
                deadline
                == min(instant(a["created_at"]) + timedelta(minutes=10), instant(a["starts_at"])),
                "Hold deadline differs from C03",
            )
            require(
                (deadline > now) == (a["status"] != "expired"),
                "Hold status disagrees with fixed clock",
            )
        if a["payment_id"]:
            p = get("payments", a["payment_id"])
            same(a, p, "appointment_id tenant_id patient_id")
            require(
                p["purpose"] == "consultation" and p["amount"] == a["consultation_price"],
                "Wrong booking charge",
            )
        if a["status"] in {"confirmed", "in_progress", "completed", "no_show"}:
            require(
                a["payment_id"]
                and p["status"] == "succeeded"
                and a["payment_resolution"] == "confirmed",
                "Confirmed workflow lacks payment",
            )
        if a["payment_resolution"] == "refund_required":
            require(
                a["payment_id"]
                and p["status"] == "succeeded"
                and p["resolution"] == "refund_required",
                "Missing refund flag",
            )
    require(all(count == 1 for count in occupied.values()), "Double-booked slot")
    for s in data["slots"]:
        get("clinics", s["tenant_id"])
        get("subjects", s["doctor_id"])
        require(
            instant(s["ends_at"]) - instant(s["starts_at"]) == timedelta(minutes=30),
            "Non-fixed slot",
        )
        require(
            (s["availability"] == "unavailable") == bool(occupied[s["slot_id"]]),
            "Slot availability mismatch",
        )
        if instant(s["ends_at"]) > now:
            require(
                member(s["doctor_id"], s["tenant_id"], "doctor"),
                "Future slot doctor lacks active membership",
            )
    for i, s in enumerate(data["slots"]):
        for other in data["slots"][i + 1 :]:
            if s["doctor_id"] == other["doctor_id"]:
                require(
                    s["ends_at"] <= other["starts_at"] or other["ends_at"] <= s["starts_at"],
                    "Doctor slot overlap",
                )
    for m in data["catalogue"]:
        get("clinics", m["tenant_id"])
        require(type(m["active"]) is bool, "Catalogue active must be boolean")
    item_ids = set()
    for p in data["prescriptions"]:
        a = get("appointments", p["appointment_id"])
        same(p, a, "tenant_id patient_id doctor_id")
        require(
            a["status"] in {"in_progress", "completed"} and p["items"],
            "Prescription outside consultation",
        )
        require(
            instant(a["starts_at"]) <= instant(p["issued_at"]) <= instant(a["ends_at"]),
            "Issue outside consultation",
        )
        for item in p["items"]:
            require(
                set("prescription_item_id medication_id quantity instructions display_name".split())
                <= item.keys(),
                "Incomplete prescription item",
            )
            require(
                item["prescription_item_id"] not in item_ids | all_ids,
                "Duplicate prescription item/resource",
            )
            item_ids.add(item["prescription_item_id"])
            m = get("catalogue", item["medication_id"])
            same(p, m, "tenant_id")
            require(type(item["quantity"]) is int and item["quantity"] > 0, "Invalid quantity")
    for n in data["notes"]:
        same(n, get("appointments", n["appointment_id"]), "tenant_id patient_id doctor_id")
    for doc in data["documents"]:
        same(doc, get("prescriptions", doc["prescription_id"]), "tenant_id appointment_id")

    ordered = set()
    for o in data["orders"]:
        p = get("prescriptions", o["prescription_id"])
        same(o, p, "tenant_id appointment_id patient_id")
        require(
            p["status"] == "issued" and p["prescription_id"] not in ordered,
            "Invalid/duplicate prescription order",
        )
        ordered.add(p["prescription_id"])
        require(len(o["items"]) == len(p["items"]), "Order omitted prescription items")
        prescribed = {i["prescription_item_id"]: i for i in p["items"]}
        seen_items = set()
        for item in o["items"]:
            require(
                set(
                    (
                        "prescription_item_id medication_id display_name "
                        "quantity unit_price line_total"
                    ).split()
                )
                <= item.keys(),
                "Incomplete order item",
            )
            ident = item["prescription_item_id"]
            require(
                ident in prescribed and ident not in seen_items, "Unprescribed/duplicate order item"
            )
            seen_items.add(ident)
            same(item, prescribed[ident], "medication_id quantity display_name")
            require(
                type(item["quantity"]) is int and item["quantity"] > 0, "Invalid order quantity"
            )
            require(
                money(item["line_total"]) == item["quantity"] * money(item["unit_price"]),
                "Wrong line total",
            )
        subtotal = sum(money(i["line_total"]) for i in o["items"])
        require(subtotal == money(o["medication_subtotal"]), "Wrong medication subtotal")
        q = get("quotes", o["quote_id"])
        same(o, q, "order_id tenant_id medication_subtotal delivery_fee total")
        require(money(q["total"]) == subtotal + money(q["delivery_fee"]), "Wrong quote total")
        if q["status"] == "active":
            require(instant(q["expires_at"]) > now, "Active quote expired")
        require(
            instant(q["created_at"])
            < instant(q["expires_at"])
            <= instant(q["created_at"]) + timedelta(minutes=10),
            "Invalid quote validity",
        )
        if o["payment_id"]:
            pay = get("payments", o["payment_id"])
            same(o, pay, "order_id tenant_id patient_id quote_id")
            require(
                pay["amount"] == q["total"] and q["status"] == "accepted",
                "Payment/quote snapshot mismatch",
            )
            require(
                instant(pay["updated_at"]) < instant(q["expires_at"]),
                "Successful fixture charge after quote expiry",
            )
        if o["status"] in {"paid", "submitting", "dispatched", "delivered"}:
            require(
                o["payment_id"] and pay["status"] == o["payment_status"] == "succeeded",
                "Unpaid progressed order",
            )
        if o["delivery_id"]:
            delivery = get("deliveries", o["delivery_id"])
            same(o, delivery, "order_id tenant_id")
            require(
                o["medicine_status"] == "ready" and o["payment_status"] == "succeeded",
                "Delivery bypassed paid AND ready",
            )
            require(
                instant(delivery["created_at"]) >= instant(pay["updated_at"]),
                "Delivery preceded payment",
            )
            if o["status"] == "delivered":
                require(delivery["status"] == "delivered", "Order/delivery status mismatch")
    for p in data["payments"]:
        get("clinics", p["tenant_id"])
        get("subjects", p["patient_id"])
        require(
            type(p["commission_bps"]) is int and 0 <= p["commission_bps"] <= 10000,
            "Invalid snapshot commission",
        )
        if p["purpose"] == "consultation":
            require(
                p["appointment_id"] and p["order_id"] is None and p["quote_id"] is None,
                "Wrong consultation links",
            )
            a = get("appointments", p["appointment_id"])
            same(p, a, "tenant_id patient_id")
            base = money(p["amount"])
        else:
            require(
                p["appointment_id"] is None and p["order_id"] and p["quote_id"],
                "Wrong medication links",
            )
            o = get("orders", p["order_id"])
            same(p, o, "tenant_id patient_id quote_id")
            base = money(o["medication_subtotal"])
        require(
            money(p["commission_amount"]) == base * p["commission_bps"] // 10000,
            "Wrong commission base/split",
        )
        require(
            money(p["amount"]) == money(p["commission_amount"]) + money(p["clinic_amount"]),
            "Wrong payment split",
        )
    for q in data["quotes"]:
        get("orders", q["order_id"])
        same(q, get("orders", q["order_id"]), "tenant_id")
    for delivery in data["deliveries"]:
        o = get("orders", delivery["order_id"])
        same(delivery, o, "tenant_id")
        require(o["delivery_id"] == delivery["delivery_id"], "Unlinked delivery")

    event_routes = {
        "consultation_payment_succeeded.v1": ("telelink.billing", "payments", "payment_id"),
        "medication_payment_succeeded.v1": ("telelink.billing", "payments", "payment_id"),
        "appointment_confirmed.v1": ("telelink.scheduling", "appointments", "appointment_id"),
        "prescription_issued.v1": ("telelink.clinical-records", "prescriptions", "prescription_id"),
        "document_ready.v1": ("telelink.document", "documents", "document_id"),
        "delivery_status_changed.v1": ("telelink.fulfilment", "deliveries", "delivery_id"),
    }
    event_ids = set()
    for e in data["events"]:
        source, collection, key = event_routes[e["DetailType"]]
        require(
            e["Source"] == source and e["EventBusName"] == "telelink-local", "Wrong C05 event route"
        )
        detail = json.loads(e["Detail"])
        walk(detail)
        require(
            set(detail)
            == {"event_id", "schema_version", "occurred_at", "tenant_id", "correlation_id", "data"},
            "Wrong envelope",
        )
        require(
            type(detail["schema_version"]) is int
            and detail["schema_version"] == 1
            and e["Time"] == detail["occurred_at"]
            and instant(e["Time"]) <= now,
            "Wrong event version/time",
        )
        require(detail["event_id"] not in event_ids, "Duplicate event ID")
        event_ids.add(detail["event_id"])
        payload = detail["data"]
        resource = get(collection, payload[key])
        same(detail, resource, "tenant_id")
        require(
            instant(e["Time"]) >= instant(resource["created_at"]),
            "Event preceded resource creation",
        )
        if collection == "payments":
            link = "appointment_id" if resource["purpose"] == "consultation" else "order_id"
            require(set(payload) == {"payment_id", link, "amount"}, "Wrong success payload")
            same(payload, resource, f"{link} amount")
            require(resource["status"] == "succeeded", "Success event for unsuccessful payment")
            require(
                (link == "appointment_id") == e["DetailType"].startswith("consultation_"),
                "Wrong payment event purpose",
            )
        elif collection == "prescriptions":
            require(
                set(payload) == {"prescription_id", "appointment_id"}, "Wrong prescription payload"
            )
            same(payload, resource, "appointment_id")
            require(resource["status"] == "issued", "Unissued event")
        elif collection == "documents":
            require(
                set(payload) == {"document_id", "prescription_id", "appointment_id"},
                "Wrong document payload",
            )
            same(payload, resource, "prescription_id appointment_id")
            require(resource["status"] == "ready", "Unready document event")
        elif collection == "deliveries":
            require(set(payload) == {"delivery_id", "order_id", "status"}, "Wrong delivery payload")
            same(payload, resource, "order_id status")
        else:
            require(set(payload) == {"appointment_id"}, "Wrong appointment payload")
            require(resource["payment_resolution"] == "confirmed", "Unconfirmed event")
    require(
        {e["DetailType"] for e in data["events"]} == set(event_routes),
        "Missing C05 event type coverage",
    )
    for case in data["access_cases"]:
        subject = get("subjects", case["subject_id"])
        a = get("appointments", case["appointment_id"])
        own = subject["subject_id"] == a["patient_id"] and "patient" in subject["global_roles"]
        doctor = subject["subject_id"] == a["doctor_id"] and member(
            subject["subject_id"], a["tenant_id"], "doctor"
        )
        administrative = (
            member(subject["subject_id"], a["tenant_id"], "clinic_admin")
            or "platform_admin" in subject["global_roles"]
        )
        require(
            case["action"] in {"appointment.read", "clinical.read"},
            "Unsupported fixture access case",
        )
        allowed = own or doctor or (case["action"] == "appointment.read" and administrative)
        require(
            case["expected_allowed"] == allowed
            and case["expected_http_status"] == (200 if allowed else 404),
            "Wrong access expectation",
        )
    for scenario in data["scenarios"]:
        get(scenario["collection"], scenario["resource_id"])
    return ", ".join(f"{len(data[name])} {name}" for name in FIELDS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", type=Path, default=Path(__file__).with_name("telelink.json")
    )
    args = parser.parse_args()
    try:
        data = json.loads(args.path.read_text(encoding="utf-8"))
        summary = validate(data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Invalid fixture: {error}", file=sys.stderr)
        return 1
    print(f"Valid synthetic fixtures at {data['as_of']}: {summary}.")
    print(
        f"{len(data['events'])} C05 events and {len(data['access_cases'])} access examples checked."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
