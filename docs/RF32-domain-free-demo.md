# RF32 domain-free AWS demo

Issue #335. Deploy the managed AMD64 layout using the shared W01 demo state.
No Route53 zone, custom domain or ACM certificate is required in this mode.
The default named-domain configuration remains available.

The generated CloudFront hostname uses AWS's default viewer certificate/policy;
AWS reports its minimum protocol as TLSv1. Custom-domain certificates retain the
explicit TLSv1.2_2021 policy. HTTPS remains mandatory for the private service route,
and normal browser routes redirect HTTP to HTTPS. Use synthetic demo data.

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

The selected deployment root is `infra/envs/demo`, with W01's
`demo/terraform.tfstate` key. The standalone examples remain review/reference
compositions; do not apply them against the same resources. Copy its tfvars and
backend examples into ignored operator files and initialize the shared backend.
The dev root remains a separate unprovisioned skeleton.

Actual apply/health outcomes and remaining acceptance gates are recorded in the
PR. Operator account settings, secrets, plans/state and release metadata remain
in ignored local files. W01 bootstrap state is backed up privately in the shared
versioned state bucket; its root still uses local state as documented by W01.

The first real bootstrap exposed that boto3 clients support `close()` but not a
direct context manager. Bootstrap and Lambda secret loading use `contextlib.closing`;
a real botocore client with a stubbed response covers the regression offline.
Rebuild images containing the shared package before enabling Lambda functions.

## Demo accounts

The demo root runs the account seed when workloads are first enabled, when
re-enabled after a pause, or when the seed task definition changes. Run the
database bootstrap and migrations first. Terraform uses Node.js and the AWS CLI
from the operator environment for this step. Set `AWS_PROFILE` to the same demo
profile used for the apply. Operators need permission to run the seed ECS task
and pass its roles.

The seed provisions a patient, doctor, clinic admin and platform admin, with
one synthetic clinic. It preserves existing accounts and application records.
The AWS demo uses the same shared password as the local demo. Use the Terraform
`platform.demo_login_secret` output to locate the generated usernames in Secrets
Manager and share them privately with authorized demo operators.

To rerun the seed independently, save the demo root's `terraform output -json`
to an ignored local file and run
`node dev/release/seed-demo.mjs <demo-output.json>` from the repository root.
