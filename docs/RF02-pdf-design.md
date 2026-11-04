# RF02: clinic PDF design

Issue #244; draft PR #263. Owner: NorbertLoh. Status: in progress until merge.

Prescription, receipt and medical certificate rendering now share an A4 clinic
letterhead, patient/reference/issue details, privacy footer and numbered pages.
The design follows the supplied form-style examples in black and white: centred
clinic letterhead and uppercase titles, thin rules, white backgrounds and boxed
patient details. Prescriptions use separate medicine, directions and quantity
columns; receipts use itemised SGD amounts and a ruled total-paid section; MCs
have a bordered certification area, inclusive absence dates, optional notes and
a boxed clinic/issuing-clinician section. Only available source fields are used;
the examples' logos, government links, QR codes and credentials are not copied.

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

The design applies to newly rendered PDFs. Normal worker generation retains
already-ready documents and its idempotency rules. At the user's explicit request,
the three known local demo PDFs were backed up and refreshed separately, retaining
their source details and warning/no-charge text. Patient download links were
verified after the refresh. This is not an automatic rewrite of issued documents.

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
