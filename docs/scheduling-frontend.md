# S07 scheduling frontend integration

Issue: #111. Dependencies S04 and U06–U08 are merged.

Connect the doctor timetable, clinic booking and role appointment screens to the
existing scheduling service. Resolve identity and memberships from identity `/me`;
server authorization remains authoritative. Use the existing public slot and
authenticated hold, detail and cancellation contracts without contract changes.

The Vite scheduling proxy will target localhost port 8003, with an optional
`SCHEDULING_API_TARGET` override. Billing checkout remains B07. A real hold must
never be described as a paid or confirmed appointment.

Verification and final setup instructions will be recorded here before review.
