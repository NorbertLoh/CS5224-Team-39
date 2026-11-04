# I02 local journey: booked pair -> consultation -> saved prescription -> private PDF

Status: verified locally on 21 October 2026 with real services, a real Stripe
test payment, live two-way video and no fixtures. AWS operation is out of scope (W-tasks).

## Stack

Start from the [I01 local stack](I01-local-journey.md), then add the services below
using their existing guides:

- Video: [V04 booked video](V04-booked-video.md) and
  [consultation admission](../services/consultation/ADMISSION.md), plus the
  signalling HTTPS proxy (`services/signalling`, `compose.yaml` + `compose.app.yaml`).
- Records and catalogue: [records frontend](records-frontend.md).
- Documents: [document frontend](document-frontend.md) and the P02 worker.

The new schemas (`consultation`, `clinical_records`, `fulfilment`, `document`) are
provisioned in the same `telelink-clinic-postgres` container with each service's
`scripts/create-local-schema.sql`, then migrated to head (consultation `0002`,
clinical records `0005`, fulfilment `0005`, document `0003`).

Seven processes are added to I01's thirteen:

| Process | Command (from the service directory) |
| --- | --- |
| consultation API (8004) | `python -m app` |
| clinical records API (8005) | `python -m app` |
| clinical records event publisher | `python -m app.publish_events` |
| fulfilment API (8006, catalogue) | `python -m app` |
| document API (8007) | `uvicorn app.main:create_app --factory --port 8007 --no-access-log` |
| document PDF worker | `python -m app.worker` |
| document event publisher | `python -m app.publish_events` |

After the one-time setup, `dev/local_stack.ps1 start` (Windows PowerShell) starts the
containers and all twenty processes in the background; `status` and `stop` check and
stop them. Logs go to `.local/stack/`. Pass `-StripeCli <path>` when `stripe` is not on `PATH`.

Vite runs with `npm run dev -- --host 0.0.0.0` so the signalling proxy container
can reach it. The browser uses **https://localhost:8443** (Caddy's local CA), which
serves the app, the API proxy and the admitted PeerServer from one origin.

## Configuration notes

- **Cognito callback:** set root `.env` `COGNITO_CALLBACK_URL=https://localhost:8443/auth/callback`
  and `COGNITO_LOGOUT_URL=https://localhost:8443/`, add `https://localhost:8443` to
  `COGNITO_CORS_ORIGINS`, recreate Floci and rerun bootstrap. Pool and client IDs
  are unchanged. `http://127.0.0.1:5173` stays registered by `cognito.sh`, which the
  e2e checkers now use for their logins. `http://localhost:5173` sign-in stops
  working until the callback is switched back.
- **Stripe return:** billing `SERVICE_CHECKOUT_SUCCESS_URL`/`CANCEL_URL` point to
  `https://localhost:8443/patient/checkout`, so the paid booking returns to the same origin.
- **Consultation host:** consultation needs `SERVICE_HOST=0.0.0.0` so the signalling
  container reaches it through `host.docker.internal:8004`. Use only on a trusted
  development machine.
- **Service keys** (each distinct, at least 32 bytes), matched pairwise:

  | Key | Holder A | Holder B |
  | --- | --- | --- |
  | consultation -> records | consultation `SERVICE_RECORDS_SECRET` | records `SERVICE_CONSULTATION_SECRET` |
  | consultation -> identity | consultation `SERVICE_IDENTITY_SECRET` | identity `SERVICE_CONSULTATION_SECRET` |
  | consultation -> scheduling | consultation `SERVICE_SCHEDULING_SECRET` | scheduling `SERVICE_CONSULTATION_SECRET` |
  | consultation -> billing | consultation `SERVICE_BILLING_SECRET` | billing `SERVICE_CONSULTATION_SECRET` |
  | signalling -> consultation | consultation `SERVICE_SIGNALLING_SECRET` | signalling `.env` `SIGNALLING_SECRET` |
  | document -> records | records `SERVICE_DOCUMENT_SECRET` | document `SERVICE_RECORDS_SECRET` |
  | records -> identity | records `SERVICE_IDENTITY_DOCUMENT_SECRET` | identity `SERVICE_RECORDS_SECRET` |
  | records -> tenant | records `SERVICE_TENANT_DOCUMENT_SECRET` | tenant `SERVICE_RECORDS_SECRET` |
  | fulfilment -> records | records `SERVICE_FULFILMENT_SECRET` | fulfilment `SERVICE_RECORDS_SECRET` |
  | fulfilment -> billing | fulfilment `SERVICE_BILLING_SECRET` | billing `SERVICE_FULFILMENT_SECRET` |

  Records, fulfilment and document each also need their own cursor secret.
- **Python 3.12+:** new venvs no longer include `setuptools`, so the documented
  `pip install --no-deps --no-build-isolation -e ../../packages/python_common` fails
  with `BackendUnavailable`. Drop `--no-build-isolation` locally. CI uses Python 3.10 and is unaffected.
- **Join window:** admission opens ten minutes before the appointment start, and
  the doctor can start (enabling clinical writes) only from the start time. Book a
  slot that starts soon; the 48-cell doctor timetable allows any half-hour.
- **Catalogue:** prescriptions require an active catalogue item. There is no
  catalogue UI, so seed one through the real fulfilment API:
  `services/identity/.venv/Scripts/python.exe tests/e2e/check_i02_journey.py seed-catalogue <tenant_id>`.

## Journey

All browser steps ran on `https://localhost:8443` as the Floci demo accounts, using
a local Playwright script (the project's `@playwright/test`) with fake camera and
microphone devices and a test-only certificate exception. The script is not
committed (broad browser automation is deferred).

1. **Catalogue (API):** `check_i02_journey.py seed-catalogue` added
   "Paracetamol 500 mg tablet" to I01 Journey Clinic.
2. **Book and pay:** the doctor added a 21 Oct 00:30 SGT slot. The patient booked it and
   paid through hosted Stripe test Checkout (card 4242). The appointment
   `dfb8baf9-0a06-4732-85c1-df89d6ff53a7` was confirmed, and the I01 checker passed (7/7).
3. **Join (00:20, inside the join window):** the patient and doctor each opened
   *Open video consultation*, enabled the camera/microphone and joined. Each side
   received the other's remote video (640x480 frames). Both participants joined
   again in fresh browser sessions during the run and reconnected each time; an
   explicit in-room leave/rejoin was not exercised.
4. **Start (00:30):** the doctor selected *Start clinical consultation*. Scheduling
   moved the appointment to `in_progress`, enabling clinical writes.
5. **Records:** the doctor saved a consultation note. They added the catalogue medication
   (quantity 10, dosing instructions), saved the draft and selected *Issue prescription*.
6. **Complete:** the doctor selected *Complete consultation* without an MC. The
   patient's room closed and showed *Consultation completed*, with the
   prescription PDF *Ready to download*.
7. **Download:** on the patient dashboard, *Download PDF* fetched a fresh signed
   URL and the browser saved `<document_id>.pdf` (41,855 bytes). The same download worked from
   `http://127.0.0.1:5173`. The PDF reads "Private and confidential", I01 Journey
   Clinic, Patient: Local Patient, Doctor: Local Doctor, and Paracetamol 500 mg tablet,
   quantity 10, with the instructions.

## Evidence

| Hop | Observed |
| --- | --- |
| consultation session | `completed`; started 00:30:09, ended 00:39:11 SGT |
| scheduling appointment | `completed` |
| clinical records | 1 note saved; prescription `21ca147c-...` issued 00:34 SGT; MC decision finalized as not selected |
| records outbox -> Floci EventBridge | `prescription_issued.v1` published, 0 retries |
| document worker | inbox recorded the event 2 s later; `prescription_pdf` stored as `ready` in private S3 |
| document outbox | `document_ready.v1` published, 0 retries |
| access audits | records service-read and document access audits recorded |

The re-runnable backend check passed all four assertions:

```text
> services/identity/.venv/Scripts/python.exe tests/e2e/check_i02_journey.py verify dfb8baf9-0a06-4732-85c1-df89d6ff53a7
PASS  appointment completed
PASS  prescription issued for this appointment
PASS  prescription PDF ready for the patient
PASS  signed download returns a PDF
appointment=dfb8baf9-0a06-4732-85c1-df89d6ff53a7 prescription=21ca147c-7262-47b3-b53e-782b48f010ff document=d1179fd3-c4ba-52e0-b936-951e2543d1c3 pdf_bytes=41855
```

`verify` reads only as the patient and fetches the signed URL without the API
bearer token, as the browser does. It exits non-zero if any check fails.

## Findings and limits

- **Raw identifiers remain in records views.** The doctor's records workspace
  header (Patient, Clinic) and the patient's Prescriptions list (Clinic) show
  UUIDs. This is the same gap as the appointment views fixed in I01 (#235).
  Suggested follow-up.
- **The in-call room covers the records form.** With the call connected, the doctor
  room is a full-screen dialog. At a 1400x1000 viewport, the remote video element
  intercepted clicks on the records form inside it. The note/prescription/completion
  steps were therefore performed from a second doctor tab, while both participants
  stayed connected in their rooms. Suggested follow-up: check the in-call layout
  for writing records during a live call.
- **Start confirmation is not visible.** After *Start clinical consultation*
  succeeds, the refreshed appointment swaps the button to *Complete consultation*,
  and the "Consultation started." message is not shown. Minor UX follow-up.
- **The download button's accessible name** is "Download Prescription PDF". The
  visible text is "Download PDF".
- Not covered: AWS, TURN/relay across independent networks (RF01), physical
  devices, and MC issuance (completion here recorded "no MC").
