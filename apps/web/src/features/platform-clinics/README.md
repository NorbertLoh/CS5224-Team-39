# U04 platform clinic administration

The platform clinic approval and commission page uses the real identity and
tenant services. No fixture fallback is used.

Route: `/platform-admin/clinics`. Requires a signed-in `platform_admin` identity.
Uses the existing frontend Cognito configuration and tenant/identity API proxies.

Implementation and verification are in progress under issue #80.
