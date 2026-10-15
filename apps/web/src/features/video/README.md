# Video room (U11)

Patient: `/patient/consultation`. Doctor: `/doctor/consultation`.
These role-protected previews use synthetic consultation context. The patient
sees a video room; the doctor also sees the U12 note and prescription form.

X01 (#56 / PR #57) is incomplete. Remote media, PeerJS/TURN connectivity,
appointment admission and booked-appointment integration are not implemented.
This UI work does not complete those dependencies or U11's remote-call verification.
V02/V03/V04 remain responsible for admission and appointment integration.

Local camera/microphone access requires localhost or HTTPS and browser permission.
No media is recorded or sent to another participant by this preview. Doctor form
saves are in memory and reset when leaving the page or reloading.

## Run and review

Use the existing local frontend configuration in `apps/web/.env` (see its
`.env.example`), with Floci on 4566 and identity on 8001. From `apps/web`, run
`npm ci` and `npm run dev`. Sign in as `patient@example.test` or
`doctor@example.test`, password `LocalDemo123!`, and open the matching route
above. Both dashboards also link to the consultation preview. At desktop width,
the doctor form sits beside the video; narrow screens stack the form below it.

Join preview expands the room to fill the browser area. Leave, Escape and the
explicit disconnect test return it to its original position and stop local
tracks. Rejoin expands it again; enable devices separately to request browser
permission. Mute/camera controls change local track availability. The doctor
form remains mounted across these transitions so notes and prescription entries
are retained. Desktop doctors retain the form beside the video, with independent
form scrolling; narrow screens stack the two areas. Keyboard focus stays within
the expanded room and returns to the join/rejoin button after leaving.
Route navigation/reload resets form contents.

Verification: frontend lint, TypeScript/production build and all 65 tests pass.
Browser checks passed for real local patient/doctor login, role denial in both
directions, patient form exclusion, doctor note save and retention on simulated
disconnect, desktop side-by-side layout and 390px mobile layout without horizontal
overflow. Physical camera/mic permissions, hardware toggles, device-loss cleanup
and rejoin with devices were not exercised in the browser. Remote calling and
cross-network/TURN verification remain blocked by X01, not counted as complete.

Expanded-room browser checks: patient join/rejoin fills the browser area; Leave
and Escape restore the embedded layout and focus; Tab wraps inside the room.
