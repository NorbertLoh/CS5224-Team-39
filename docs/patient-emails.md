# RF51 patient lifecycle emails

Issue #373 / PR #374. Receipts are emailed only after Billing has verified a
successful payment and Document has stored its private PDF. Consultation mail
names the clinic, amount, paid time/reference and appointment time when available.
Medication mail includes the total paid, including delivery; its attached receipt
contains the breakdown. A receipt confirms a charge, independently of any late
booking/payment recovery or later refund.

Issued MC and prescription PDFs use normal signed-in document-page links, without
attachments, bearer tokens or signed S3 URLs. Their notices wait for Scheduling to
report the consultation completed. No MC is invented when none was issued.
Clinic prescription pricing produces a single readiness event per prescription;
repeat saves do not produce another email. That notice also waits for consultation
completion, rechecks current issuance/pricing/unpaid status, and links to the
signed-in medication order review. The patient confirms delivery and the final
total before creating/resuming payment. A voided, unpriced, paid or cancelled
source does not produce a misleading payment request.

Existing delivery events now describe their current status and link to the order.
Scheduling cancellations and provider-verified full refunds produce separate
notices. No refund is represented as completed while pending/uncertain. There is
no rescheduling API: existing cancellation and new-booking flows produce their
own notices; this change does not create a rescheduling feature.

## Durable preparation and sending

Notification migration `0003_lifecycle_emails` adds source-event references and
preparation-attempt counts. It retains existing jobs and their send states. It
stores metadata events only, never PDFs, rendered email bodies or clinical text.
Each new job rechecks the resource owner and current Identity mailbox before
sending. Superseded work becomes `skipped`. Clinical notices waiting for completion
defer without spending send attempts. Other preparation failures defer at the
configured interval for up to ten attempts, then remain failed with
`source_unavailable`. No SES request occurs during preparation.

An SES claim is still committed before transmission. Definitive throttling alone
is automatically retried within the existing send-attempt limit. Ambiguous SES
responses/crashes remain `uncertain`; no automatic resend. Provider acceptance
is not proof of inbox delivery. Existing pending legacy jobs retain generic copy;
historical paid events/documents are not replayed by deployment.

Receipt PDF bytes come only from the purpose-authenticated Document endpoint,
which verifies tenant, patient, receipt kind, private storage and document integrity.
Clinical PDFs cannot be fetched through this endpoint. SES MIME attachments are
bounded to 5 MB and a fixed UUID-based filename. `ses:SendRawEmail` is granted only
to the dispatch role and the existing sender identity. No bucket access is added
to Notification.

## Configuration and deployment

Generate one distinct 32+ byte secret pairing: Billing
`SERVICE_NOTIFICATION_SECRET` / Notification `SERVICE_BILLING_SECRET`. For AWS
Secrets Manager use `notification_secret` and `billing_secret` JSON keys,
respectively; preserve all other fields. Set Notification `SERVICE_BILLING_URL`.
Local Compose setup provisions the pair and URL. Existing scheduling, document,
fulfilment and identity notification credentials are reused with their own
audiences. Update the local notification EventBridge pattern through normal setup.

Back up the database and migrate Notification before enabling updated consumers.
Rebuild Billing, Scheduling, Fulfilment, Document and Notification service images
and both Lambda images, including the shared Python package. Apply the updated
EventBridge routes and scoped SES permission through the shared demo Terraform.
Preserve RF50's API concurrency 64 and current image pins for unaffected services.
No frontend build or other schema migration is required.

The AWS SES sandbox still requires verified sender and recipient addresses (or
SES simulator destinations). `.test` demo mailboxes cannot prove real delivery.
Use captured local MIME/tests and an explicitly authorized verified recipient for
inbox acceptance testing. Do not replay historical patient events just to test.
