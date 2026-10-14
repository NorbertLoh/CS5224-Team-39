# Clinic profile editor

`/clinic-admin/clinics/<tenant UUID>/profile` always reads and saves through the
tenant API. Home links are based on the signed-in user's live identity roles.
The backend checks current clinic-admin/platform-admin access on every operation.

- `ClinicProfileEditor.tsx`: backend load, saved/draft state, Save and Discard.
- `ClinicProfileForm.tsx` and `ProfileField.tsx`: fields, validation and feedback.
- `LogoUpload.tsx`: upload/remove and image preview below the file picker.
- `BrandingPreview.tsx`: preview while editing.
- `logo-api.ts`: authenticated profile and S3-backed logo requests.
- `profile.ts`: field validation and exact SGD conversion.

Save commits fields to PostgreSQL and shows confirmation beside the buttons.
Failed saves retain edits and show an error. Discard restores the last saved
values. Logo upload, replacement and removal save immediately, independently of
Save/Discard. Replacement uses one S3 key; the unversioned bucket retains no old
image. PNG/JPEG/WebP, 2 MB, 4 megapixels; server normalises to PNG and strips metadata.

No browser profile persistence or demo mode remains. The environment flag only
selects local or AWS API/Cognito settings. See [backend setup](../../../../../docs/clinic-backend.md).
