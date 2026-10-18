# Video room (U11)

Patient: `/patient/consultation`. Doctor: `/doctor/consultation`.
The video area is a role-protected preview. The patient sees a video room; the
doctor also sees the real R04 appointment records workspace. Select an actual
appointment before viewing/saving records; the video preview does not admit or
start that appointment. See [records setup](../../../../../docs/records-frontend.md).

X01 (#56 / PR #57) is incomplete. Remote media, PeerJS/TURN connectivity,
appointment admission and booked-appointment integration are not implemented.
This UI work does not complete those dependencies or U11's remote-call verification.
V02/V03/V04 remain responsible for admission and appointment integration.

Local camera/microphone access requires localhost or HTTPS and browser permission.
No media is recorded or sent to another participant by this preview. Doctor form
saves and issuance now use the real records API and survive reload. Unsaved edits
are discarded when switching appointments, navigating away or reloading.

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
Route navigation/reload reloads saved records; only unsaved edits are discarded.

Historical U11 preview verification: frontend lint, TypeScript/production build and all 65 tests passed.
Browser checks passed for real local patient/doctor login, role denial in both
directions, patient form exclusion, doctor note save and retention on simulated
disconnect, desktop side-by-side layout and 390px mobile layout without horizontal
overflow. Physical camera/mic permissions, hardware toggles, device-loss cleanup
and rejoin with devices were not exercised in the browser. Remote calling and
cross-network/TURN verification remain blocked by X01, not counted as complete.

Expanded-room browser checks: patient join/rejoin fills the browser area; Leave
and Escape restore the embedded layout and focus; Tab wraps inside the room.

## Code structure

`VideoRoom` coordinates the role layout and call state. `CallStage` displays
participant placeholders and the local video; `CallControls` handles media and
leave buttons. `useLocalMedia` owns devices, while `useExpandedRoom` owns focus,
keyboard navigation and background scrolling. The doctor workspace composes
`ConsultationNoteForm`, `PrescriptionEditor` and `PrescriptionItemFields`.

These files use Prettier 3.6.2 with `--single-quote --no-semi`. After the component
split, lint, TypeScript/build, all 65 tests and Prettier checks passed; the patient
join/leave browser flow and focus restoration were verified again.

U11 continuation: live reusable room transport, tracked under issue #126. V04 retains booked-appointment/admission wiring.
