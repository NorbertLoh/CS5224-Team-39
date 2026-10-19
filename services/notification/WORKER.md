# N02 notification worker

Consumes the three C05 notification events into durable jobs before acknowledging
SQS, then sends queued jobs through N01's SES adapter. Recipient lookup uses
purpose-specific service credentials and owner-service APIs. Verification pending.
