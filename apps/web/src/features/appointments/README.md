# Appointments

S07 uses real authorized scheduling list/detail/cancellation APIs for patient,
doctor and clinic admin workspaces. Lists support cursor pagination and Singapore
dates; detail polling reflects server status, expiry and refund review. Metadata
names are the booking-time snapshots from the API; appointments booked before
scheduling migration `0007` may have no saved names.
Appointment cards and details resolve missing clinic/doctor names through the
public paginated directories. Booking-time names take precedence; unavailable
directory names use readable labels instead of identifiers.
See [setup, boundaries and verification](../../../../../docs/scheduling-frontend.md).

`AppointmentSchedule` coordinates current identity and role scope; `AppointmentGrid`
and `AppointmentCell` display each patient booking once with its full time range;
staff retain the half-hour timetable. `LiveAppointmentDetails` fetches detail
and handles eligible cancellations; `AppointmentDetails` renders server metadata.
`display` contains pure formatting/grid helpers.
