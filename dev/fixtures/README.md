# F14: shared synthetic fixtures

[`telelink.json`](telelink.json) is the canonical shared development dataset for
the merged [C01-C05 contracts](../../contracts/README.md). It contains two active
clinics, nine subjects (two patients, three active doctors, a former doctor,
two clinic admins and a platform admin), and seven memberships. One doctor works
at both clinics; the former doctor's membership is revoked but appointment
history remains. Clinic A charges SGD 25, clinic B SGD 30, both with 10% commission.

The linked resources include 11 fixed slots, 10 appointments, 10 consultation or
medication payments, a two-item demo catalogue, three placeholder notes/issued
prescriptions, three orders/quotes/documents and one completed delivery. All text,
identities, amounts and records are synthetic. Notes/instructions are nonclinical
placeholders; no real provider credentials, tokens, addresses or signed URLs are
included.

## Use and validate

From the repository root, with Python 3.10+ (standard library only):

```powershell
python dev/fixtures/validate.py
python -m unittest discover -s dev/fixtures -p "test_*.py"
```

The validator checks required resource fields, UUID/UTC/money shapes, tenant and
participant references, memberships, slot capacity/overlap, hold deadlines,
prescription quantities, order/quote totals, commission snapshots, payment/readiness
gates and C05 event payloads. Invalid data exits nonzero with the first error.
Validate a modified development copy with:

```powershell
python dev/fixtures/validate.py .local/telelink-fixtures.json
```

Backend tests/adapters can load the file without dependencies:

```python
import json
from pathlib import Path

fixtures = json.loads(Path("dev/fixtures/telelink.json").read_text(encoding="utf-8"))
patient_id = fixtures["subjects"][0]["subject_id"]
appointments = [a for a in fixtures["appointments"] if a["patient_id"] == patient_id]
response = {"items": appointments, "next_cursor": None}
```

Frontend fixture adapters can import the same JSON or copy a development projection
under their feature. Adapt the arrays to the C01 direct-resource/pagination response
shape; the top-level file is a dataset, not an API response. For `/identity/me`,
combine a subject with their active memberships. For public clinic profiles,
omit `commission_bps` and `review_reason`. Never return the entire dataset from a
public API. Doctor listings come from active doctor memberships, not global roles.
Scenario/access expectations help build UI states; filtering arrays does not
implement production authorization or prove tenant isolation.

## Fixed clock and repeatability

`as_of` is **2026-10-13 03:00 UTC (11:00 Singapore time)**. The file is a static
snapshot: tests and mock UI countdowns should use that fixture clock. Live holds
and quotes are valid relative to it, even when the wall clock advances. Do not
disable real server expiry checks to accommodate these fixtures. To use a different
fixture date, shift all related timestamps consistently in a development copy,
then validate it. Stable UUIDs and amounts must remain consistent across consumers.

Reading/loading this JSON has no side effects. Reset mock state by reloading the
canonical file; keep modified runtime copies in ignored `.local/`. There is no
database loader yet: owning service tasks must map their own rows through their
service-local seed/migration tooling. No shared script writes across service schemas.

`cognito_sub` values start with `synthetic-` and are fixed fixture identities;
they are **not** the runtime Floci subjects created by F13. A04/service-local seed
tools must explicitly map actual verified Cognito subjects to these application
IDs. This file grants no login, membership or arbitrary-header authentication bypass.

## Walkthrough scenarios

Use `scenarios` entries to locate resources without relying on array order. Their
`collection` and `resource_id` identify an object in the named array.

| Scenario | Expected development view |
| --- | --- |
| `completed_journey` | Completed clinic-A consultation, prescription/PDF, paid and delivered order |
| `patient_across_clinics` | Patient A has clinic-A history and a confirmed clinic-B booking |
| `live_hold` | Patient B has a hold expiring at 03:08 UTC |
| `pending_checkout` | Payment pending; original hold expires at 03:05 UTC |
| `late_payment_slot_reallocated` | Late successful charge needs refund; a newer patient-B hold owns the slot |
| `cancelled_booking` | Cancelled appointment with failed payment attempt |
| `ready_before_paid` | Clinic-B order is ready, but unpaid; active SGD 24 quote expires at 03:04 UTC |
| `paid_before_ready` | Clinic-A SGD 15 order is paid, but medicine is not ready; no delivery exists |
| `revoked_doctor_history` | Former assigned doctor no longer has staff access to historical appointment |

`access_cases` contains 11 expected appointment/clinical read outcomes, including
unrelated patients, the wrong clinic, another doctor in the same clinic, revoked
staff, and clinic/platform administrators without clinical access. These are
fixture expectations, not implementation tests of an authorization service.

## Events and scope

`events` holds seven C05 PutEvents entries covering all six event types and a
second medication success for the paid-before-ready order. Detail is a JSON
string, matching the existing contract transport fixtures; identifiers, amounts
and timestamps match this dataset's committed facts. The EventBridge bus name is
the local default; configured adapters must substitute their own bus name.

These historical events are useful for isolated mocked consumers. Do not send
them into running workflow workers backed by an unrelated database: resources
must exist through each owning service first, and workers must enforce inbox
deduplication. The dataset, validator and mock flows do not establish payment,
delivery, authentication or integrated persistence completion. F16 and I01-I03
retain their real verification scope.
