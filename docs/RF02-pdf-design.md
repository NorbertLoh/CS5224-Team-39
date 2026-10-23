# RF02: clinic PDF design

Issue #244; draft PR #263. Owner: NorbertLoh. Status: in progress until merge.

Prescription, receipt and medical certificate rendering now share an A4 clinic
letterhead, patient/reference/issue details, privacy footer and numbered pages.
Prescriptions use a medicine/directions/quantity table; receipts use itemised SGD
amounts and a distinct total-paid band; MCs separate the certification statement,
inclusive absence dates, optional notes and issuing clinician.

## Review samples

These contain synthetic, explicitly labelled sample data only:

- [Prescription](samples/rf02/prescription.pdf)
- [Receipt](samples/rf02/receipt.pdf)
- [Medical certificate](samples/rf02/medical-certificate.pdf)

Regenerate offline from `services/document`, using the service environment:

```powershell
python -m scripts.render_samples --output ../../docs/samples/rf02
```

No configuration or dependency changes are required. The existing bundled Vera
fonts, unsupported-glyph rejection, escaped text and non-patient PDF metadata are
preserved. Template-data contracts, source validation, storage and download APIs
are unchanged. Missing clinic addresses or registration numbers are omitted;
signatures and credentials are never invented. Receipt generation wiring remains
outside RF02.

The design applies to newly rendered PDFs. Already-ready documents retain their
stored bytes; this change does not rewrite issued documents or bypass generation
idempotency.

## Verification

- Full document suite: **105 passed**, using a new disposable PostgreSQL database,
  restricted document role and the required sentinel fixture. Database removed
  after the run; the local application's database was not reset.
- Ruff check and format check pass for all changed Python files.
- All three one-page synthetic samples rendered and visually reviewed. Adjusted
  the prescription number column to avoid a wrapped header.
- Regression coverage exercises a single 18,000-character prescription direction,
  repeated medicine headers, 100 receipt items with the final total, long MC
  notes and patient names, and absent optional issuer fields.
- Existing tests continue to cover markup escaping, glyph rejection, timestamp
  formatting, metadata privacy and invalid snapshot rejection.

The suite emits one existing Starlette/httpx deprecation warning.
