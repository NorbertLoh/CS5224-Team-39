# P03 document API

Task #147 adds authenticated document listing and short-lived download URLs.

The API follows clinical-record access policy: the owning patient or the assigned doctor with a current active clinic membership. Clinic/platform administrators receive no clinical document access by default. Scheduling remains authoritative for appointment ownership; document metadata must match its current context.

Implementation and verification are in progress. UI remains U14; AWS privacy/expiry evidence remains #54.
