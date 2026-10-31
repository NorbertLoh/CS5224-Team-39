# RF26 background jobs

Reusable Terraform module for document/notification Lambda workers, bounded SQS
consumption, scheduled durable email dispatch and operational alarms. Requires
existing networking, queues, secrets, document storage, SES identity and service APIs.

Inputs and cutover: [RF26 guide](../../../docs/RF26-serverless-workers.md).
`tests/controls.tftest.hcl` contains synthetic example inputs and mocked plan checks.
No environment root is created or modified by this module.
