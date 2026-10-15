# Failed consumer jobs and replay (M04)

M02 and M03 are merged in PRs #97 and #99. This task verifies the remaining
failure path: a failed handler rolls back, SQS moves the message to its processing
DLQ, and an operator replays the unchanged event after fixing the failure.

Verification and the operator procedure are being prepared on this draft branch.
No shared queue, database or event contract changes are required.
