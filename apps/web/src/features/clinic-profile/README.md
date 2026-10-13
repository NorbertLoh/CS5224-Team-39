# U02 clinic profile editor

Fixture-only clinic administrator previews at `/clinic-admin/clinics/:slug/profile`.
Edit name, description, colour, optional logo URL and consultation fee. Keep slug,
status and commission outside writable fields. Saves are local demo state; real
clinic access checks/navigation belong to U05 and tenant API integration to A11.

The page will use small form and preview components with contract-aligned validation.
