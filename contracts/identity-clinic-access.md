# C02: identity, clinics and appointment access

This proposed contract follows [C01](api-conventions.md) and the service boundaries
in `plan.md`. It defines interfaces for A04-A10, S01/S04 and consuming U01-U08
features; it does not implement authentication, persistence or authorization.
Consumer review is required before merge. Examples are synthetic.

## Identity and membership resources

Identity owns `subject_id` (application UUID), `cognito_sub` (opaque external ID),
`display_name`, `global_roles`, and clinic memberships. A patient or doctor ID is
the subject's application UUID, not a separate identity. `global_roles` permits
`patient` and `platform_admin`; `doctor` and `clinic_admin` are clinic membership
roles. A subject can have several roles and memberships. Cognito groups seeded
by F13 are login fixtures, not an authoritative source of application permissions.
Never accept request headers, token group names or browser state as membership
proof. Resolve verified Cognito `sub` against current identity records.

A membership has required `membership_id`, `subject_id`, `tenant_id`, `roles`
(nonempty unique subset of `doctor`, `clinic_admin`), `status` (`active` or
`revoked`), `created_at` and `updated_at`. One membership per subject/tenant;
PUT replaces its role set and reactivates a revoked membership. Revocation retains
history. Membership changes must invalidate cached access or use a bounded cache
TTL; authorization cannot rely on indefinitely cached membership.

All fields above are required. Self identity includes only active memberships.
Emails/contact details are not needed in these interfaces. IDs and instants use
C01. Request bodies have only the writable fields explicitly listed below.

| Identity route (prefix `/api/v1/identity`) | Request and response | Authorization |
| --- | --- | --- |
| GET `/me` | Identity plus `memberships` array; 200 | Verified subject; unknown subject returns 403 `identity_not_provisioned` |
| GET `/clinics/{tenant_id}/memberships` | C01 paginated memberships; optional `status`; ordered `created_at`, `membership_id` ascending | Active clinic admin of this tenant or platform admin |
| PUT `/clinics/{tenant_id}/memberships/{subject_id}` | `{ "roles": ["doctor"] }`; returns membership, 201 for new / 200 for existing | Same administrators; target subject and clinic must exist |
| DELETE `/clinics/{tenant_id}/memberships/{subject_id}` | Revoke membership; 204, including repeated revoke | Same administrators |

Membership mutations do not grant global roles. Platform-admin provisioning is an
operator-controlled path, outside these public APIs. A clinic admin cannot remove
or demote the last active clinic admin: 409 `last_clinic_admin`. The check includes
concurrent mutations. Creating a clinic assigns its creator a clinic-admin
membership through identity's API with retry/idempotency, never a tenant-service
write into identity tables. The clinic remains non-bookable until provisioning
and approval succeed. Cross-service provisioning implementation belongs to A08/A10.

## Clinic and branding resources

Tenant owns `tenant_id`, immutable unique `slug`, `name`, `status`, `branding`,
`consultation_price`, `commission_bps`, `created_at`, `updated_at`. Status is
`pending_review`, `active`, `rejected` or `suspended`. Only `active` clinics accept
new slots/holds/bookings. Suspending a clinic does not silently cancel existing
appointments or revoke participants' access to their own records.

`branding` requires `primary_color` (`#RRGGBB`), `logo_url` (HTTPS URL or null)
and `description` (plain text). No embedded HTML or arbitrary CSS. Consultation
price is C01 Money in SGD. Commission is an integer basis-point rate, 0-10000;
billing snapshots it at checkout (C03). Public profiles omit commission and
administrative review details. An admin profile includes all clinic fields plus
`review_reason` (plain text or null).

| Tenant route (prefix `/api/v1/tenant`) | Request and response | Authorization |
| --- | --- | --- |
| GET `/clinics` | Public active profiles, C01 pagination; order `name`, `tenant_id` ascending | Public |
| GET `/clinics/by-slug/{slug}` | Active public profile; 200, otherwise 404 | Public |
| GET `/clinics/{tenant_id}/doctors` | Active doctors: `doctor_id`, `display_name`; C01 pagination, order `display_name`, `doctor_id` ascending | Public for active clinic; no membership IDs or private identity fields |
| POST `/clinics` | `slug`, `name`, `branding`, `consultation_price`; admin profile, 201 (200 for identical same-creator retry); server sets pending_review, commission default 0 | Verified subject; server assigns creator's admin membership |
| GET `/clinics/{tenant_id}` | Admin profile; 200 | Active clinic admin or platform admin |
| PATCH `/clinics/{tenant_id}` | Optional `name`, complete `branding`, `consultation_price`; admin profile, 200 | Active clinic admin or platform admin; no status/commission input |
| GET `/admin/clinics` | Admin profiles; optional `status`, C01 pagination ordered `created_at`, `tenant_id` ascending | Platform admin |
| POST `/clinics/{tenant_id}/review` | `decision` (`approve`, `reject`, `suspend`), `reason` (required nonempty text for reject/suspend, otherwise null); admin profile, 200 | Platform admin |
| PUT `/clinics/{tenant_id}/commission` | `{ "commission_bps": 1000 }`; admin profile, 200 | Platform admin; audit previous/new value |

A08 creation commits a pending clinic before provisioning the creator membership.
If provisioning fails, 503 instructs the same creator to retry the identical slug
and payload; the clinic stays hidden and non-bookable until acknowledged.
Identical retries reuse the clinic/membership; after successful provisioning they
also require the creator's current admin access. Other duplicate slugs or changed
creation payloads return 409 `slug_taken`. Revoked creators cannot use this retry
to restore membership or read the admin profile.

Review transitions: pending_review -> active/rejected; rejected -> active on
explicit approval; active -> suspended; suspended -> active on approval. A
repeated decision matching current status returns that resource without duplicate
audit/event side effects. Rejecting active/suspended clinics or suspending a
non-active clinic returns 409 `invalid_clinic_transition`. Reason and actor are
audited. No automated licence verification is implied.

## Appointment access

Scheduling owns appointment tenant, patient and doctor links. All appointment
resources require `appointment_id`, `tenant_id`, `patient_id`, `doctor_id`,
`slot_id`, `status`, `starts_at`, `ends_at`, `created_at`, `updated_at`. C03 defines
booking fields/states and scheduling routes. A patient may book at multiple
clinics; that creates no clinic-wide membership or history access.

| Caller | Appointment metadata | Clinical notes/prescriptions/documents | Mutations |
| --- | --- | --- | --- |
| Patient | Own appointments across clinics | Own appointment-scoped records/documents | Book/cancel own appointment under C03; cannot set doctor, payment truth or clinical state |
| Doctor | Assigned appointments AND active doctor membership in owning clinic | Assigned appointment context only, same membership requirement | Clinical write within consultation context; cannot access another doctor's patients merely by clinic membership |
| Clinic admin | Appointments in active clinic memberships | No clinical notes or document content by default | Scheduling administration and medicine readiness where owning contract permits |
| Platform admin | Operational appointment metadata across clinics | No clinical records/documents by default | Clinic review/commission; no implicit clinical/consultation actions |

Users with several roles can satisfy any permitted policy, but every request
must establish the relevant policy. Deleted/revoked staff lose staff access;
the patient's access persists. Membership does not authorize video admission:
V02 also checks actual participants, appointment/payment state and join window.
Record/document reads require an audit record. A platform operational response
does not include clinical content or patient contact/address fields.

### Internal access decision

POST `/api/v1/identity/access-decisions` is service-only. Require authenticated
service identity with an allowlist for the requested action; network location
alone is insufficient. Body requires `subject_id`, `tenant_id`, `action` and
`resource` (`appointment_id`, `patient_id`, `doctor_id`). Supported actions:
`appointment.read`, `appointment.cancel`, `clinical.read`, `clinical.write`,
`medicine.ready`. Appointment fields must come from the authenticated scheduling
service's resource context, not a public browser body. The endpoint is not exposed
through public ingress. It checks current subject roles/memberships and the above
matrix, returning 200 `{ "allowed": true, "reason": "own_appointment" }` or
`{ "allowed": false, "reason": "not_authorized" }`. Reasons are safe codes;
unknown actions/invalid context are 422. `clinical.write` is doctor-only;
`medicine.ready` is clinic-admin-only; cancellation also needs C03 state checks.
An access decision is not a reusable bearer credential. Owning services must
verify resource tenant/participants and enforce domain state at mutation time.
The endpoint never permits unauthenticated callers to probe resource existence.

## Errors and consumer checks

Missing/invalid access token -> 401. Authenticated but forbidden collection/action
-> 403; inaccessible tenant/resource IDs -> 404 `not_found`, identical to missing
resources. This concealment applies before mutation state validation. Public
inactive clinic lookups return 404. A validated authorized booking into an inactive
clinic returns 409 `clinic_not_active`. Duplicate slug -> 409 `slug_taken`.
Invalid body/filter/cursor -> C01 422. Lists must filter at source by authorized
scope, and bind cursors to subject, current selected tenant and filters.

[`examples/access.json`](examples/access.json) provides self identity, an active
public clinic, membership, appointment context and access decisions including
cross-clinic and unrelated-patient denials. These fixed fixture subjects are not
F13 Cognito `sub` values; A04 must resolve actual runtime `sub` values explicitly.
F14 supplies the larger shared dataset after contract review/merge.

Review with an identity/clinic/scheduling or UI consumer: verify multi-clinic
staff selection, revoked membership, last-admin conflict, unrelated patient 404,
clinic-admin clinical denial and platform metadata-only access. No consumer
review or live authorization check has been completed by writing these examples.
