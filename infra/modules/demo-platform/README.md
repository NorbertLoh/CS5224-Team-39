# Singapore demo platform

Complete reusable demo composition for RF27 / #316 / merged PR #317. Defaults are
single-replica, single-AZ compute, small ARM Fargate tasks, one shared private
ElastiCache Redis node with TLS/encryption and one
shared NAT/TURN host. The root region must be `ap-southeast-1`.

`redis_mode="managed"` is the default; no Redis container image is required in
that mode. The single `cache.t4g.micro` has no replica or automatic failover.
`redis_mode="sidecar"` remains an explicit single-task cost-saving alternative
and requires the digest-pinned `redis` image. Local Compose is unchanged.

Setup, verified pricing assumptions, scaling limits and teardown:
[Singapore demo guide](../../../docs/RF27-singapore-demo.md).
Example inputs: [sg-demo](../../examples/sg-demo/terraform.tfvars.example).
W01 PR #233 owns the actual environment/backend skeleton; those files are untouched.

`enable_workloads=false` is the safe configuration phase, not a no-cost mode.
Publishing `images` registers bootstrap/migration tasks without starting services.
Enable workloads only after the one-off database setup and migrations succeed.
