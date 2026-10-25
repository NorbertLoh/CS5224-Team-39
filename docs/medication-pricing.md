# Typed medications and clinic-admin pricing (RF12)

Doctors enter any medication name in the prescription textbox. A valid autosave
reuses a matching active clinic medication or registers an unpriced reference.
Registration is case-insensitive and serialized for concurrent/retried requests.
The prescription retains the normal medication UUID and trusted name, so issuance,
document generation and dispensing projection contracts remain unchanged.

Clinic admins open **Clinic administration -> Medications & prices**, choose their
clinic, and set each medicine's dispensing unit and SGD unit price. Only active
owning-clinic admins may change prices. New medicines start at **Price needed**,
with `unit_price: null`; no price or free item is invented. An explicit admin price
of 0.00 is permitted by the existing nonnegative-price policy.

Prescribing/issuing does not require a price. Opening an order or making a new
quote fails with `409 medication_unpriced` until every medicine is priced. The
patient gets a specific waiting-for-clinic-pricing message. Existing checkout
snapshots, paid orders, commission, delivery and provider flows stay unchanged.

Setup: apply fulfilment migration 0006 explicitly, then rebuild/restart the
fulfilment API and web. The migration only makes catalogue `unit_price_minor`
nullable; it preserves existing prices. Its downgrade refuses while unpriced rows
exist rather than inventing prices. Back up live service data before migration.
No new environment variables. The admin panel is on the existing dashboard;
shared frontend routing and RF11 navigation/lifecycle files are unchanged.

Checks: 99 focused fulfilment API/order/quote/persistence checks passed in a
separate disposable database, including concurrent name replay, tenant/role
isolation, admin-only pricing and unpriced-order/quote gates. Ruff and frontend
lint, TypeScript and production build passed. Local browser/API evidence follows
in the linked RF12 PR; sandbox payment and courier calls are not required.

Live Tailscale browser checks verified an arbitrary typed medication autosaves and
survives reload, appears as Price needed for the owning admin, accepts an explicit
SGD 1.25/test-unit price and preserves that price when the doctor re-enters the name
with different casing. Fractional cents were rejected. Twenty clinical upstream
checks passed, including unpriced-reference lookup. The live prescription remains
a draft; no issuance, checkout payment or courier call was made for this check.
