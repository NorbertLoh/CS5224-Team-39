# Clinical records storage (R01)

Clinical records owns appointment-scoped notes, prescriptions and their items.
This task provides PostgreSQL models and service-local Alembic migrations only.
Authenticated routes and read auditing follow in R02; transactional issuance
events follow in R03. API shapes remain defined by `contracts/prescription-order-quote.md`.

Implementation and verification are in progress in the linked R01 draft PR.
