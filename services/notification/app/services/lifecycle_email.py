"""Prepare current owner-verified copy; clinical documents remain behind sign-in."""

from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from app.services.templates import EmailMessage, render_email, validate_app_url


def local_time(value):
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(ZoneInfo("Asia/Singapore"))
        .strftime("%d %b %Y, %I:%M %p SGT")
    )


def prepare_email(event, recipient, directory, app_url):
    context = recipient.context
    base = validate_app_url(app_url)
    link = base + "/patient"
    attachment = None
    kind = event.detail_type
    if kind == "document_ready.v1":
        link = base + "/patient/documents"
        if event.data.payment_id:
            if context.kind != "receipt_pdf" or context.purpose not in {
                "consultation",
                "medication_delivery",
            }:
                raise ValueError("Invalid receipt context")
            if (
                not context.clinic_name
                or context.amount_minor is None
                or context.amount_minor < 0
                or context.currency != "SGD"
            ):
                raise ValueError("Receipt details unavailable")
            purpose = (
                "Consultation" if context.purpose == "consultation" else "Medicines and delivery"
            )
            title = purpose + " payment confirmed"
            body = (
                f"{purpose} paid to {context.clinic_name}. "
                f"Amount: SGD {Decimal(context.amount_minor) / 100:.2f}. "
                f"Paid: {local_time(context.paid_at)}. "
                f"Payment reference: {context.payment_id}. Your receipt PDF is attached."
            )
            attachment = directory.receipt(event, recipient.subject_id)
            if context.purpose == "consultation" and context.starts_at:
                body += " Appointment time: " + local_time(context.starts_at) + "."
        elif event.data.medical_certificate_id:
            title, body = (
                "Your MC is ready",
                "Your doctor has issued a medical certificate. Sign in to view and download it.",
            )
        else:
            title, body = (
                "Your prescription is ready",
                "Your doctor has issued a prescription. Sign in to view it. "
                "We will notify you when the clinic has priced the medicines.",
            )
    elif kind == "prescription_priced.v1":
        title, body = (
            "Your medicines are ready for payment",
            "The clinic has priced your prescribed medicines. Sign in to review the prices, "
            "confirm delivery details and the final total, then continue to secure payment.",
        )
        link = (
            base + "/patient/medication-orders?prescription_id=" + str(event.data.prescription_id)
        )
    elif kind == "appointment_cancelled.v1":
        title, body = (
            "Your appointment was cancelled",
            "Your appointment has been cancelled. Any refund is confirmed separately "
            "once it succeeds. Sign in to review its status.",
        )
    elif kind == "payment_refunded.v1":
        if context.amount_minor is None or context.amount_minor < 0 or context.currency != "SGD":
            raise ValueError("Refund details unavailable")
        title, body = (
            "Your refund is confirmed",
            f"Your refund of SGD {Decimal(context.amount_minor) / 100:.2f} has been confirmed. "
            f"Payment reference: {event.data.payment_id}. Your bank may take time to show it.",
        )
    elif kind == "delivery_status_changed.v1":
        labels = {
            "submitted": "Courier assigned",
            "picked_up": "Out for delivery",
            "delivered": "Delivered",
            "cancelled": "Delivery cancelled",
            "failed": "Delivery needs attention",
            "unknown": "Delivery status needs confirmation",
        }
        title = labels.get(context.status, "Your delivery has an update")
        body = title + ". Sign in to view the current medicine delivery details."
        link = base + "/patient/medication-orders?order_id=" + str(event.data.order_id)
    elif kind == "appointment_confirmed.v1":
        title, body = "Your booking is confirmed", "Your appointment booking is confirmed."
        if context.clinic_name:
            body += " Clinic: " + context.clinic_name + "."
        if context.starts_at:
            body += " Appointment: " + local_time(context.starts_at) + "."
    else:
        return render_email("document_ready", app_url)
    return EmailMessage(
        title,
        body + "\n\nSign in to TeleLink Health: " + link + "\n",
        f'<p>{escape(body)}</p><p><a href="{escape(link, quote=True)}">'
        "Sign in to TeleLink Health</a></p>",
        attachment,
        "receipt-" + str(getattr(event.data, "payment_id", "")) + ".pdf" if attachment else None,
    )
