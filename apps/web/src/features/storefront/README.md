# Clinic storefront

`/clinics/<slug>` reads the active clinic from the tenant API and current doctor
summaries from identity through tenant. No fixture import or fallback is shipped
in the browser. Failures show retry; missing/inactive clinics show unavailable.
Both lists use C01 pagination; doctor order is display name, then doctor ID.

Small components handle the header, introduction, consultation card, doctor list
and footer. `ClinicStorefront` loads the clinic; `DoctorDirectory` loads doctor
pages. Colour comes from the persisted `branding.primary_color`.

AWS logos use the stored public HTTPS asset URL. Local logos use tenant's public
branding endpoint backed by private Floci S3. Only approved, provisioned clinics
with a logo are exposed. Booking/payment remain unimplemented.

See [backend configuration](../../../../../docs/clinic-backend.md).
