# Reusable AWS platform

The active [demo root](../../envs/demo/README.md) uses this module's `managed`
profile in domain-free AMD64 mode. Read the [demo architecture](../../../docs/demo-architecture.md)
and [production target](../../../docs/production-architecture.md) for separate
diagrams, traffic flows and limits. The defaults below describe the compact
reference, not the active team deployment.

For production-oriented AWS services/scaling with demo capacity defaulted to one, use
[`sg-managed`](../../examples/sg-managed/README.md). Its `managed` deployment profile
adds separate private API ingress and worker groups, NAT Gateway with TURN ASG,
production settings and data protections. Capacities and RDS/cache/AZ failover
settings are configurable; a future-two overlay is provided. It is not a claim
of verified production readiness. The defaults below describe `sg-demo`.

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
The environment root owns state/operator inputs; do not create a competing root
for the same resources. See [database operations](../../../docs/database/README.md)
for schema ownership, bootstrap and explicit migration tasks.

`enable_workloads=false` is the safe configuration phase, not a no-cost mode.
Publishing `images` registers bootstrap/migration tasks without starting services.
Enable workloads only after the one-off database setup and migrations succeed.

All eight business API containers use Uvicorn `--limit-concurrency 64` (RF50).
This ceiling counts open connections as well as active request tasks. The former
limit of eight rejected normal patient/clinic polling with HTTP 503 responses.
This changes no task count, CPU/memory allocation or autoscaling maximum, so
allocated Fargate baseline capacity is unchanged. Actual request, network and
logging usage can still affect charges. Lambda/FIFO worker concurrency remains
separate and defaults to one; signalling uses its existing Node.js runtime.
