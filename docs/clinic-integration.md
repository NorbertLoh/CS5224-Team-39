# A11 clinic integration

Scope: verify the clinic storefront, profile, staff management and platform
administration together against real identity and tenant APIs. Setup is documented
in [clinic-backend.md](clinic-backend.md). No runtime fixtures are used.

## Changes

- Profile and logo saves refresh clinic queries through one small cache helper.
  Platform review also refreshes the doctor directory when availability changes.
- Unfiltered platform-list pagination accepts its signed null status scope while
  still rejecting missing scope, a different user, and a different status filter.
- Fresh local tenant configuration includes its separate scheduling service key,
  so readiness succeeds. Existing `.env` files remain preserved; follow the
  upgrade note in [clinic-backend.md](clinic-backend.md).

## Repeatable local HTTP check

After starting the three services described in the setup guide, run:

```powershell
services/identity/.venv/Scripts/python.exe dev/check_clinic_integration.py
```

The script uses Floci PKCE logins for the four documented synthetic accounts and
requests through Vite's `/api/v1` proxy to real identity/tenant services,
PostgreSQL and private Floci S3. It creates two uniquely named synthetic clinics
and retains them suspended for inspection. It never resets schemas or edits
existing clinics. Membership changes are confined to those new clinics. Refresh
tokens obtained by the script are revoked when it finishes.

Verified on 14 October 2026:

- Creator membership provisioning; pending/rejected/suspended clinics hidden from
  storefront and public doctor APIs; reject, approve and suspend transitions.
- Profile name, branding and exact SGD price persist and appear in public reads;
  logo upload, public image stream and removal use real storage.
- Commission saves persist and public profiles omit administrative fields.
- Email staff assignment, role replacement, revoke/reactivate, current identity
  membership changes and immediate public doctor-directory changes.
- Last-administrator protection; anonymous, patient, doctor and cross-clinic
  authorization denials; staff and unfiltered platform cursor pagination.

The complete HTTP check passed. Both API readiness endpoints returned 200 after
the local scheduling-key correction. Frontend: 32 tests, ESLint, TypeScript and
production build passed. Tenant cursor regression: one focused test passed;
tenant and changed Python files passed Ruff. No migrations or dependencies changed.

## Browser walkthrough

The real clinic account completed PKCE login and role navigation. A new synthetic
clinic appeared in Manage clinics; the profile form saved a name/fee change and
retained it after reload. Staff management loaded the real clinic name and
account details, assigned the doctor by email and saved both doctor/admin roles.
The browser tool stalled on the native revocation confirmation; revoke/reactivate
were verified through the real HTTP check instead.
The remaining platform browser interaction and responsive visual checks remain
unverified; the real platform APIs were covered by the complete HTTP check.

AWS deployment checks remain unverified and belong to the infrastructure tasks.
