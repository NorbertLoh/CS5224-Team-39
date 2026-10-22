# Doctor availability

S07 connects this timetable to scheduling APIs using the signed-in doctor's active
clinic memberships. It reads real weekly slots and persists add/remove actions.
See [setup, behavior and verification](../../../../../docs/scheduling-frontend.md).

`AvailabilityEditor` selects the current clinic; `DoctorTimetable` owns live queries,
selection and writes. `WeeklyTimetable`, `TimetableCell` and `useTimetableSelection`
retain pointer/keyboard interactions. `timetable` and `slot-time` are pure helpers.
