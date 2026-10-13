# F16: Floci compatibility and persistence

Issue #43 is assigned to NorbertLoh and In progress. F11–F13 and A01–A03
are merged. This verification covers the local APIs required by the plan:
Cognito, S3, EventBridge, SQS, SES and Secrets Manager.

Use a separate Compose project and volume for verification so checks do not
consume existing development messages or alter users. Compare the seeded
resources and test data before and after graceful restart and container
recreation, without running bootstrap between comparisons.

Record the tested release/image, reproducible commands, results and known
differences here before review. This does not establish real AWS compatibility.
