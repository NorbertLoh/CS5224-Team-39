# Public edge and cache semantics

Reusable CloudFront module with private S3 frontend access, public clinic caching,
uncached protected APIs/signalling and frontend-only SPA rewriting. The platform
also supplies private VPC origins in domain-free mode; see the
[demo traffic flow](../../../docs/demo-architecture.md). The named-origin input
contract below is used by the [managed reference](../../examples/sg-managed/README.md).

## Named-origin inputs and caching

`infra/modules/public-edge` creates a distribution around an existing private S3
frontend bucket, regional API endpoint and HTTPS signalling origin. Inputs include
`frontend_bucket_domain` (regional S3 REST endpoint), `frontend_bucket_arn`,
`api_domain`, `signalling_domain` and `name_prefix`. Custom aliases require a
matching ACM certificate in `us-east-1`. Origin DNS names must have matching TLS
certificates; signalling admission and origin restrictions remain W11 concerns.
The module owns the frontend bucket policy; do not also manage that policy in W04.
The bucket owner must retain public-access blocks and encryption.

Public rules precede `/api/*` and cache GET/HEAD only:

- `/api/v1/tenant/clinics`
- `/api/v1/tenant/clinics/by-slug/*`

Both successful tenant endpoints send
`Cache-Control: public, max-age=0, s-maxage=60, must-revalidate`. CloudFront requires
origin opt-in (`default_ttl=0`, `min_ttl=0`) and caps freshness at 60 seconds. Its
public cache key includes `limit` and `cursor`, plus compression. These endpoints
must stay identical for all viewers; test coverage compares anonymous and
Authorization-bearing reads. The origin request policy preserves authentication
because `POST /clinics` shares the listing path; POST and other writes are never
cached. Do not add viewer-specific fields, cookies or additional response-varying
query parameters without changing this design. Intended browser access is through
the same CloudFront origin; cross-origin CORS caching needs separate review.

Other API paths and signalling have caching disabled, and tenant responses default
to `no-store`. SPA rewriting is attached only to frontend navigation; API errors
are not converted to index.html. Error caching TTL is zero. Clinic edits/suspension
may remain visible publicly for up to 60 seconds. Booking, payment and staff-access
decisions still use authoritative service reads. For immediate public removal,
invalidate the listing and affected profile paths via the existing deployment role.
The distribution does not invalidate on every clinic write.
