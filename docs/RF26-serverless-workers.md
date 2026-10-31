# RF26: Lambda workers, public caching and operational controls

Tracks issue #314. Implementation in progress; no AWS resources have been deployed.

Scope: SQS-triggered document generation and notification intake, scheduled durable
notification dispatch, bounded concurrency, public clinic CloudFront caching, queue
and outbox monitoring. Local Compose workers and transactional outbox publishers
remain available. Infrastructure is supplied as isolated modules; W01 PR #233 owns
the environment skeleton. AWS integration requires the planned networking, service
endpoints, RDS, queues, SES, buckets and IAM dependencies.
