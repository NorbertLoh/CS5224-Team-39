# Release images and frontend artifacts (RF31)

These tools now support the [active domain-free demo](../infra/envs/demo/README.md).
The original preparation evidence below predates deployment. Production acceptance
remains separate; see the [production target](production-architecture.md).

Issue #332. Preparation only: no AWS upload, Terraform plan/apply, DNS setup or
provider transactions. RF26/RF27 already supply service images and infrastructure.
This adds a release inventory, local builds and later digest handoff; W12 and the
AWS deployment/verification tasks remain open. W01 PR #233 owns shared state.

## Local preparation

Requires Node 24+, Git and Docker Desktop/Engine with Buildx and AMD64 build support.
No AWS CLI or credentials are needed for local builds.
If Docker is not on PATH, set `RELEASE_DOCKER` to its executable path. Run from the
repository root, on a clean committed revision:

```powershell
node --test dev/release/release.test.mjs
node dev/release/release.mjs inventory
node dev/release/release.mjs build
node dev/release/release.mjs frontend dev/release/frontend.check.json
```

The build creates twelve local images tagged
`telelink-release/<name>:<full-git-revision>` and writes metadata to ignored
`.local/releases/<revision>/`. Supply names after `build` to retry selected images.
Nine Python service images include the notification migration image. Eight run
APIs; the same images run their owning workers and one-off migrations. Signalling
is the tenth regular image. All twelve images use Linux AMD64, matching the
managed example's ECS `X86_64` setting. Document and notification Lambda images
omit provenance attestations for Lambda compatibility. Notification intake and
dispatch share the notification Lambda image with Terraform selecting commands.
Managed ElastiCache and the EC2 coturn bootstrap need no application Redis/TURN
image. The service template and development setup image are not deployed.

Local image IDs are **not** registry manifest digests. Never copy them into
Terraform. Git tags identify source; existing floating base tags mean rebuilding
later may change bytes. Retain the built images and use their published digests
for deployment and rollback. Docker cache and local images consume disk; no local
stack is restarted or pruned by this tooling.

The separate cheaper sg-demo example retains its earlier ARM64 ECS choice and is
not compatible with this AMD64 image bundle. The digest handoff rejects outputs
whose `cpu_architecture` is not `X86_64`. EC2 TURN and managed database/cache instance
families are separate from the container architecture and remain unchanged.

The frontend is a static S3 artifact, not the development Vite container.
`Dockerfile.release` runs lint, TypeScript and Vite build, exports only `dist/`,
and includes imported assets/fonts through Vite. Public logo uploads and private
documents are runtime S3 data and must not be baked into images. The supplied
`frontend.check.json` has deliberately non-deployable build-only settings. Its
successful build proves compilation, not login or AWS connectivity. A final
deployable bundle requires real public Cognito/API settings; rebuild it later.
Each frontend configuration gets its own directory keyed by a configuration hash.

## Later handoff (do not run until deployment is authorized)

1. Coordinate W01 and select one remote state/root. Do not create a competing
   state or use both sg-demo and sg-managed for the same resources. Confirm the
   real account, budget, region, service/provider settings and ownership first.
2. Provision/review the foundation with workloads disabled through the established
   RF27 process. Export `terraform output -json` into an ignored local JSON file.
   The `platform` (managed) or `demo` output supplies ECR URLs and public frontend
   settings. Do not include secret values in release metadata.
3. Authenticate Docker to the account's Singapore ECR via the operator's approved
   AWS session. For **each** inventory name, tag the local image with
   `<repositories[name]>:<full-git-revision>` and explicitly `docker push` that tag.
   ECR tags are immutable: use a new revision rather than overwriting one. Check
   scan findings before deployment and retain the previously deployed digests.
   The existing ECR policy keeps only three images; review it before relying on
   an older release for rollback, because tags do not prevent lifecycle expiry.
4. After all twelve images exist remotely, run:

   ```powershell
   node dev/release/release.mjs pin .local/platform-output.json
   node dev/release/release.mjs frontend .local/platform-output.json
   ```

   Export fresh Terraform outputs for the frontend build. RF48 adds
   `VITE_DOCUMENT_DOWNLOAD_VIA_API=true`, paired with
   `SERVICE_DOWNLOAD_VIA_API=true` in the document task definition. Build and
   publish the document image from the same release revision, pass its digest
   in the image map, and publish the rebuilt frontend after the API is healthy.
   Reusing an older image digest or frontend export will retain its older behavior.

   `pin` performs registry reads only. It validates architecture and single-image
   manifests, then writes `images.tfvars.json` with real ECR digests and
   `enable_workloads=false`. It never pushes images or invokes Terraform. Pass
   this file explicitly with `-var-file` when an operator later reviews a plan.
   Partial/missing registry builds fail without writing a new complete image map.
5. Complete secrets, DB roles/bootstrap and all nine owning-service migrations
   before enablement. Follow [the managed profile](../infra/examples/sg-managed/README.md)
   and [RF27 sequence](RF27-singapore-demo.md); never run migrations on each API
   replica startup. Verify callbacks, SES, health and AWS patient-journey gates.
6. Upload the **real-config** frontend: hashed `assets/` first with
   `public,max-age=31536000,immutable`, then remaining files with
   `no-cache,max-age=0,must-revalidate`; upload `index.html` last. Retain old hashed
   assets for cached pages/rollback (avoid `sync --delete`). Invalidate `/index.html`
   and `/` on the emitted distribution; use a broader invalidation if other
   unversioned paths changed. Preserve API errors and private bucket access.

## Domain decision

Route53/domain setup is intentionally skipped for this preparation. The frontend
can use the generated CloudFront hostname and Cognito's generated OAuth hostname.
The named `sg-managed` example requires owned signalling/internal API names and
Route53 certificate validation. RF32 subsequently added domain-free mode to
`infra/envs/demo`, using private CloudFront VPC origins and the generated hostname.
Follow that root's [instructions](../infra/envs/demo/README.md); internal HTTP hops
do not provide end-to-end application TLS.

## Verification

Record actual local build outcomes in the PR. The focused checks validate inventory
against Terraform, platform selection, required frontend configuration and secret
rejection. Local builds additionally check real dependency installation, service
packaging, architecture and static frontend output. They do not prove production
capacity, provider integrations, cross-network video or an AWS deployment.
