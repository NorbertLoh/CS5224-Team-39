# Appointments

S07 uses real authorized scheduling list/detail/cancellation APIs for patient,
doctor and clinic admin workspaces. Lists support cursor pagination and Singapore
dates; detail polling reflects server status, expiry and refund review. Metadata
names are the booking-time snapshots from the API; appointments booked before
scheduling migration `0007` fall back to identifiers.
See [setup, boundaries and verification](../../../../../docs/scheduling-frontend.md).

`AppointmentSchedule` coordinates current identity and role scope; `AppointmentGrid`
and `AppointmentCell` display half-hour cells. `LiveAppointmentDetails` fetches detail
and handles eligible cancellations; `AppointmentDetails` renders server metadata.
`display` contains pure formatting/grid helpers. Older fixture helpers and demo
filters remain test-only and are not mounted by the application.
