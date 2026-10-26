# Clinic pickup settings

Clinic admins open **Manage clinic → Settings** to save the medicine pickup
address, Singapore postcode and map coordinates of the pickup entrance. The
clinic location is required before a new delivery quotation can be calculated.
No location is invented or seeded for an existing clinic.

The same form includes **Pickup contact name** and **Pickup phone number**.
Names cannot be blank or contain control characters. Singapore numbers can be
entered as eight digits or with `+65`; spaces, parentheses and hyphens are removed,
and numbers are saved in the `+65` format required for delivery. Contact details
are stored inside the existing location JSON and audited atomically, so no new
migration is needed for the contact fields. Older location-only clients preserve
the saved contact when they omit that field.

Before preparing a courier request, the delivery worker reads the saved clinic
pickup contact through the same authenticated tenant projection. If the tenant
connection is configured, missing/invalid clinic contacts block preparation;
the worker does not silently substitute a sender from the old file directory.
An already-prepared request keeps its recorded contact details. Patient recipient
contacts remain separately required through `SERVICE_DELIVERY_CONTACTS_PATH`;
adding clinic contact fields alone does not supply a patient's name or phone.
Restart the delivery worker when deploying this integration.

Only active admins of that clinic can read/write
`GET/PUT /tenant/clinics/{tenant_id}/location`. A platform role alone is insufficient.
Updates validate Singapore coordinates, serialize on the clinic row and atomically
record the actor, previous location and new location in tenant's append-only audit.
An identical retry does not add another audit event.

## Deploy and configure

Back up tenant data, then apply tenant migration `0004` with
`python -m alembic upgrade head` before deploying the new tenant image. The migration
adds `tenant.clinic_locations` and the `clinic.location_changed` audit action.
Downgrade refuses to discard location audit history. Fulfilment has no new migration.

Set fulfilment `SERVICE_TENANT_URL` to the tenant API base, for example
`http://tenant:8000` in local Compose. Set a distinct random 32+ byte
`SERVICE_TENANT_SECRET` on fulfilment and matching `SERVICE_FULFILMENT_SECRET` on
tenant. The Compose setup helper creates this pair. Restart the affected services
after configuration. These values are server-only.

Fulfilment reads only the selected clinic's active pickup projection through
`GET /internal/clinics/{tenant_id}/delivery-location`, using a short-lived,
purpose-specific service token. A missing saved location returns
`clinic_location_missing`; an unreachable or invalid tenant response returns
`clinic_location_unavailable`. The patient sees delivery-specific guidance.

The saved clinic pickup takes precedence over file-based origins when
`SERVICE_TENANT_URL` is set. Existing deployments without that setting retain their
explicit file-based origin configuration. There is no fallback to a file origin
when the configured tenant connection fails or its clinic location is missing.

The prototype still needs `SERVICE_DELIVERY_LOCATIONS_PATH` for trusted destination
postcode coordinates and real sandbox provider credentials. Its JSON can have an
empty `origins` object when pickup comes from Clinic Settings. Destination coverage
is configured by the operator as described in
[QUOTES.md](../services/fulfilment/QUOTES.md); arbitrary address geocoding is outside
this change. The current local demo covers postcode `038983` using the documented
public landmark coordinates. No clinic pickup address was populated.

New quote requests fetch the latest saved pickup location. Quote route snapshots,
idempotent quote replays, accepted/paid orders and courier submission continue to
use the recorded route. Changing Settings does not reroute an existing paid order.

## Verification

124 tenant migration/persistence/API checks and 70 fulfilment location/quote/provider
checks passed on disposable PostgreSQL. They cover role/tenant boundaries, revoked
membership, address/coordinate validation, service authentication, audit/no-op
retries, missing locations and route snapshots across edits/replays. Backend lint
and frontend lint/typecheck/production build passed. Local tenant schema was backed
up before migration; tenant, fulfilment and web were rebuilt and are healthy.
The browser verified Settings in the clinic navbar and the empty pickup form.
No real clinic address, quote, payment or delivery was created for verification.

Pickup-contact extension: 97 tenant API/location checks and 70 fulfilment
location/dispatch checks passed on isolated PostgreSQL, plus Ruff and frontend
lint/typecheck/build. Browser verification confirmed the two contact fields and
preserved saved location. No real contact data was saved and no courier request
was submitted during verification.
