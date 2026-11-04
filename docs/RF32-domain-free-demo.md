# RF32 domain-free AWS demo

Issue #335. Deploy the managed AMD64 layout using the shared W01 demo state.
No Route53 zone, custom domain or ACM certificate is required in this mode.
The default named-domain configuration remains available.

Browser HTTPS/WSS uses the generated CloudFront hostname. Signalling and internal
API ALBs are private CloudFront VPC origins. API Gateway keeps JWT authorization
for normal browser API calls and reaches the private API ALB through its VPC Link.
CloudFront's private connection and VPC Link use HTTP within the VPC; this is not
end-to-end application TLS. Neither ALB has a public listener in domain-free mode.

Application service URLs remain HTTPS, using a separate `/service/<owner>` path
on CloudFront. A viewer-request function rejects callers whose actual viewer IP
is not one of the Terraform-owned NAT egress addresses, validates the service/path,
and rewrites it to the owning API prefix. Purpose-specific service credentials
remain mandatory in the API; the NAT allowlist does not replace authorization.
These responses are never cached. Header-supplied forwarding IPs are not trusted.

Use one state/root only. Provision foundation with workloads disabled; publish
the verified RF31 AMD64 images, populate fresh service secrets, bootstrap database
roles and run each owner's migrations before enabling workloads. Rebuild the
static frontend with emitted public settings. Do not invent sandbox provider
credentials, delivery coverage, mail verification or acceptance evidence.

Actual apply/health outcomes and remaining acceptance gates are recorded in the
PR. Operator account settings, secrets, plans/state and release metadata remain
in ignored local files. W01 bootstrap state is backed up privately in the shared
versioned state bucket; its root still uses local state as documented by W01.
