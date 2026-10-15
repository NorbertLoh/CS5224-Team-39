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
