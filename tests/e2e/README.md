# Cross-service checks

Reserved for focused integration checks when justified by implementation. I01-I05 and Q01-Q06 define the prototype walkthroughs; manual evidence is acceptable. Broad browser automation is deferred.

- `check_i01_journey.py`: submits the pending I01 clinic and verifies the resulting approved clinic, confirmed appointment and succeeded payment. See [I01 local journey](../../docs/I01-local-journey.md).
- `check_i02_journey.py`: seeds the I02 clinic catalogue and verifies the completed consultation, issued prescription and private PDF download. See [I02 local journey](../../docs/I02-local-journey.md).
- `check_i03_journey.py`: verifies the issued prescription, separate succeeded consultation/medication payments, trusted quote and one persisted sandbox submission. See [I03 local journey](../../docs/I03-local-journey.md).
- `check_q02_booking.py`: races two real patient identities for one slot, waits for
  the unchanged server deadline and verifies reallocation. Creates one synthetic
  slot and uses read-only PostgreSQL/Redis checks; cleanup uses the APIs. Run with
  scheduling's environment and `--tenant-id <active demo clinic UUID>`; allow about
  ten minutes. Use `--config-root <checkout>` when configuration is in another checkout.
  Setup, observed evidence and confirmation limits: [Q02 verification](../../docs/Q02-booking-verification.md).
