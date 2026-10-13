# A10 staff membership integration

A10 reuses the identity service's GET/PUT/DELETE membership routes and its current
role checks, per-clinic write lock and last-active-administrator guard. Identity
validates clinic existence through a narrowly scoped, authenticated tenant API.
Membership rows stay in identity; clinic rows stay in tenant.

Clinic lifecycle state does not prevent staff administration: pending, rejected
and suspended clinics still need administrators. Booking eligibility remains a
separate tenant check. No frontend or root Compose changes are included.
