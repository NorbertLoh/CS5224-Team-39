mock_provider "aws" {
  mock_data "aws_region" { defaults = { region = "ap-southeast-1" } }
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/test-worker" } }
  mock_resource "aws_lambda_function" { defaults = { arn = "arn:aws:lambda:ap-southeast-1:123456789012:function:test-worker" } }
  mock_resource "aws_sqs_queue" { defaults = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:dispatch-failures" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/lambda/test" } }
}

variables {
  name_prefix         = "rf26-test"
  environment         = "demo"
  subnet_ids          = ["subnet-0123456789abcdef0"]
  security_group_ids  = ["sg-0123456789abcdef0"]
  document_bucket_arn = "arn:aws:s3:::rf26-documents"
  ses_identity_arn    = "arn:aws:ses:ap-southeast-1:123456789012:identity/example.test"
  alarm_action_arns   = []
  workers = {
    document = {
      image_uri         = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/document@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      config_secret_arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:document-abcdef"
      concurrency       = 5
      timeout_seconds   = 120
    }
    notification-intake = {
      image_uri         = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/notification@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      config_secret_arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:notification-abcdef"
      concurrency       = 2
      timeout_seconds   = 60
    }
    notification-dispatch = {
      image_uri         = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/notification@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      config_secret_arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:notification-abcdef"
      concurrency       = 2
      timeout_seconds   = 60
    }
  }
  consumer_queues = {
    document = {
      arn                        = "arn:aws:sqs:ap-southeast-1:123456789012:document"
      dlq_arn                    = "arn:aws:sqs:ap-southeast-1:123456789012:document-dlq"
      visibility_timeout_seconds = 720
      redrive_policy             = "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-southeast-1:123456789012:document-dlq\",\"maxReceiveCount\":3}"
    }
    notification-intake = {
      arn                        = "arn:aws:sqs:ap-southeast-1:123456789012:notification"
      dlq_arn                    = "arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq"
      visibility_timeout_seconds = 360
      redrive_policy             = "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq\",\"maxReceiveCount\":3}"
    }
  }
  monitored_queues = {
    document     = { is_dlq = false }
    document-dlq = { is_dlq = true }
  }
}

run "bounded_workers" {
  command = plan
  assert {
    condition     = aws_lambda_event_source_mapping.consumer["document"].scaling_config[0].maximum_concurrency == 5 && aws_lambda_function.worker["document"].reserved_concurrent_executions == 5
    error_message = "Queue and function concurrency limits must agree."
  }
  assert {
    condition     = aws_lambda_event_source_mapping.consumer["document"].batch_size == 1 && contains(aws_lambda_event_source_mapping.consumer["document"].function_response_types, "ReportBatchItemFailures")
    error_message = "Process one job and acknowledge partial failures correctly."
  }
  assert {
    condition     = aws_scheduler_schedule.dispatch.schedule_expression == "rate(1 minute)"
    error_message = "Durable email retries require a schedule."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.outbox_age["billing"].treat_missing_data == "breaching"
    error_message = "A stopped publisher must not look healthy."
  }
}

run "reject_short_visibility" {
  command = plan
  variables {
    consumer_queues = {
      document            = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:document", dlq_arn = "arn:aws:sqs:ap-southeast-1:123456789012:document-dlq", visibility_timeout_seconds = 30, redrive_policy = "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-southeast-1:123456789012:document-dlq\"}" }
      notification-intake = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:notification", dlq_arn = "arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq", visibility_timeout_seconds = 360, redrive_policy = "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq\"}" }
    }
  }
  expect_failures = [aws_lambda_event_source_mapping.consumer["document"]]
}

run "reject_missing_redrive" {
  command = plan
  variables {
    consumer_queues = {
      document            = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:document", dlq_arn = "arn:aws:sqs:ap-southeast-1:123456789012:document-dlq", visibility_timeout_seconds = 720, redrive_policy = "" }
      notification-intake = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:notification", dlq_arn = "arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq", visibility_timeout_seconds = 360, redrive_policy = "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-southeast-1:123456789012:notification-dlq\"}" }
    }
  }
  expect_failures = [aws_lambda_event_source_mapping.consumer["document"]]
}

run "demo_recipient_sender_restriction" {
  command = apply
  variables {
    ses_identity_arn            = "arn:aws:ses:ap-southeast-1:123456789012:identity/sender@example.test"
    ses_recipient_identity_arns = ["arn:aws:ses:ap-southeast-1:123456789012:identity/patient@example.test"]
  }
  assert {
    condition = anytrue([for statement in jsondecode(aws_iam_role_policy.worker["notification-dispatch"].policy).Statement :
      try(statement.Resource == ["arn:aws:ses:ap-southeast-1:123456789012:identity/patient@example.test"] &&
        statement.Condition.StringEquals["ses:FromAddress"] == "sender@example.test" &&
      toset(statement.Action) == toset(["ses:SendEmail", "ses:SendRawEmail"]), false)
    ])
    error_message = "Recipient identity permissions must allow both email APIs only with the configured sender."
  }
  assert {
    condition = alltrue([for name in ["document", "notification-intake"] :
      !strcontains(aws_iam_role_policy.worker[name].policy, "ses:Send")
    ])
    error_message = "Only notification dispatch may send email."
  }
}

run "reject_recipient_wildcards" {
  command = plan
  variables {
    ses_identity_arn            = "arn:aws:ses:ap-southeast-1:123456789012:identity/sender@example.test"
    ses_recipient_identity_arns = ["arn:aws:ses:ap-southeast-1:123456789012:identity/*"]
  }
  expect_failures = [var.ses_recipient_identity_arns]
}

run "reject_foreign_recipient_identity" {
  command = plan
  variables {
    ses_identity_arn            = "arn:aws:ses:ap-southeast-1:123456789012:identity/sender@example.test"
    ses_recipient_identity_arns = ["arn:aws:ses:us-east-1:999999999999:identity/patient@example.test"]
  }
  expect_failures = [var.ses_recipient_identity_arns]
}
