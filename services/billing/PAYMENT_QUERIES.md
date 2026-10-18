# B05 payment queries

Implementation in progress in issue #178. Public reads will use the existing
C03 payment projection, current identity checks and C01 cursor pagination.
Patients see their own payments, active clinic admins see their clinics, and
platform admins see all payments. Doctors have no independent billing access.

Commission totals will sum immutable successful payment snapshots, excluding
refund-required and refund states. Totals are operational figures, not provider
settlement or accounting revenue. No migrations or shared contract changes are
planned.
