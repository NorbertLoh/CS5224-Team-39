# Documents UI (U14)

The patient's Documents page groups authorised documents by visit in collapsible
rows, newest visit first, with clinic, doctor, visit date/time and available PDF
counts/types. A visit can contain prescription, receipt and/or medical certificate
PDFs only when issued. Groups merge as more document pages load. Each expanded
group retains individual document states, references and signed downloads.
Patient/doctor appointment
details and the doctor's records workspace show PDFs for the selected appointment.
These views use the real P03 API, with no document fixtures in production code.

In doctor Consult, **Past documents** groups earlier PDFs by consultation.
Each collapsed visit shows its actual consultation date/time (SGT), doctor,
document count and PDF types. Expand it to see that consultation's documents
together with their statuses, references and download actions. Groups merge and
deduplicate as older pages load and sort by visit time, including PDFs generated
after the original consultation. The existing scheduling history response supplies
visit labels; no extra appointment lookups or wider access are needed.
History anchors remain attached to document list and download requests.
The empty state still allows older-page loading when more visits are available.

RF55 requires only a web rebuild; no migration, API or configuration changes.
Frontend lint/typecheck/build, probe typecheck, grouping/history-pagination/download
probe, prior history/navigation/auth probes and four video recovery checks passed.
The Tailscale web image was rebuilt and restarted healthy; live read-only browser
checks verified grouped consultation summaries and expanded prescription/receipt
actions. No clinical records or appointment/call states were changed.

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
