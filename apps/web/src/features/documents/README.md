# Documents UI (U14)

The patient dashboard lists authorised documents. Patient/doctor appointment
details and the doctor's records workspace show PDFs for the selected appointment.
These views use the real P03 API, with no document fixtures in production code.

Lists include pagination, refresh, loading, empty and error states. Pending and
failed PDFs have no download action. Each ready-PDF click obtains a new signed
URL and opens it as an attachment in the same tab, avoiding an asynchronous popup.
The URL is validated and used immediately; it is not put in query state, storage
or persistent links. A download failure allows another attempt with a fresh URL.

Identity/token/appointment/clinic changes isolate the document query cache and
cancel pending downloads when the component unmounts. P03 independently checks
the caller's current identity and appointment before returning metadata or a URL.
The frontend hides metadata on list/identity errors or mismatched context.

Configuration and verification: [document frontend setup](../../../../../docs/document-frontend.md).
