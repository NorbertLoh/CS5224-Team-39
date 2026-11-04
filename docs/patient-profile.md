# Patient profile

RF14 medicine checkout prefills these details, permits order-only edits and offers
an unchecked **Save to my profile** option. Confirmed order contacts stay fixed
when this Profile changes later. See [checkout contacts](RF14-checkout-contacts.md).

Patients open **Profile** at `/patient/profile` to save their name, Singapore
contact number, address and six-digit postcode. Eight-digit contact numbers and
`+65` numbers are accepted and normalized. The name updates the patient's current
identity display name; account IDs, email and roles are unchanged.

`GET/PUT /identity/me/patient-profile` derives ownership from the authenticated
subject, accepts no patient ID or privileged fields, and requires the patient
role. A patient without a saved profile starts with their existing name and blank
contact/address fields. Responses use `Cache-Control: no-store`; browser drafts
remain in component memory rather than persistent browser storage.

Medicine checkout uses the saved address as its initial editable destination.
Refreshes do not overwrite edits. A successful calculation retains input;
editing a quoted address still requires a new quote before payment. Profile
changes do not alter an existing quote or paid delivery route. Saving a postcode
does not add it to the prototype's supported quotation coverage directory.

## Storage and deployment

Back up identity data and apply identity migration `0003` with
`python -m alembic upgrade head` before deploying the new identity image. It adds
`identity.patient_profiles`, keyed to the subject, with phone/address/postcode
constraints. Name and profile changes commit atomically. Downgrade refuses to
discard saved profiles. Fulfilment has no new migration.

Set a distinct random 32+ byte fulfilment `SERVICE_PROFILE_SECRET` matching
identity `SERVICE_FULFILMENT_SECRET`. Fulfilment's existing `SERVICE_IDENTITY_URL`
must point to the identity API base. The Compose setup helper creates the secret
pair. Restart identity, fulfilment, web and the delivery worker after deployment.

Delivery preparation calls the service-only endpoint
`GET /internal/patients/{patient_id}/delivery-contact` with a short-lived token
for `telelink-identity-delivery`. It exposes only patient ID, current name and
phone, and requires a saved profile and patient role. Addresses and roles are not
included. With this connection configured, missing, invalid or mismatched profiles
block preparation without substituting a file recipient. Existing deployments
without the profile connection keep their explicit contact-directory behavior.
Prepared courier requests retain their recorded contact snapshot. A paid, ready
order waiting for contact details can resume after those details are saved; all
existing payment, route, delivery-fee and uncertain-submission guards remain.

## Verification

140 identity migration/persistence/API checks and 76 fulfilment profile/location/
dispatch checks passed on isolated PostgreSQL. Checks cover self-only ownership,
role restrictions, privileged-field rejection, phone/address validation, atomic
persistence, service-token purpose and minimal/matching recipient projections.
Ruff and frontend lint/typecheck/production build passed. The local identity
schema was backed up before migration; affected services are healthy. Browser
verification confirmed the Profile navbar link and form with the patient's
existing name. No patient contact data was invented, and no courier request was
submitted for verification.
