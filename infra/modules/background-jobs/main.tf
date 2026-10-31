data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  commands = {
    document              = "app.lambda_handler.handler"
    notification-intake   = "app.lambda_handler.intake"
    notification-dispatch = "app.lambda_handler.dispatch"
  }
}


resource "aws_cloudwatch_log_group" "worker" {
  for_each          = var.workers
  name              = "/aws/lambda/${var.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "worker" {
  for_each = var.workers
  name     = "${var.name_prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "worker" {
  for_each = var.workers
  role     = aws_iam_role.worker[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.worker[each.key].arn}:*"
      },
      {
        Effect   = "Allow", Action = ["secretsmanager:GetSecretValue"]
        Resource = each.value.config_secret_arn
      },
      {
        # Lambda VPC ENI operations do not support resource-level permissions.
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets", "ec2:DeleteNetworkInterface", "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses"]
        Resource = "*"
      }
      ], contains(keys(var.consumer_queues), each.key) ? [{
        Effect   = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.consumer_queues[each.key].arn
      }] : [], each.key == "document" ? [
      {
        Effect = "Allow", Action = ["s3:GetBucketPublicAccessBlock"], Resource = var.document_bucket_arn
      },
      {
        Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${var.document_bucket_arn}/*"
      }
      ] : [], each.key == "notification-dispatch" ? [{
        Effect = "Allow", Action = ["ses:SendEmail"], Resource = var.ses_identity_arn
        }] : [], length(each.value.kms_key_arns) > 0 ? [{
        Effect = "Allow", Action = ["kms:Decrypt"], Resource = each.value.kms_key_arns
    }] : [])
  })
}

resource "aws_lambda_function" "worker" {
  for_each                       = var.workers
  function_name                  = "${var.name_prefix}-${each.key}"
  role                           = aws_iam_role.worker[each.key].arn
  package_type                   = "Image"
  image_uri                      = each.value.image_uri
  architectures                  = ["x86_64"]
  timeout                        = each.value.timeout_seconds
  memory_size                    = each.value.memory_mb
  reserved_concurrent_executions = each.value.concurrency
  image_config {
    command = [local.commands[each.key]]
  }
  environment {
    variables = merge(each.value.environment, {
      SERVICE_ENVIRONMENT       = var.environment
      SERVICE_AWS_REGION        = data.aws_region.current.region
      SERVICE_CONFIG_SECRET_ARN = each.value.config_secret_arn
    })
  }
  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = var.security_group_ids
  }
  depends_on = [aws_iam_role_policy.worker]
}

resource "aws_lambda_event_source_mapping" "consumer" {
  for_each                = var.consumer_queues
  event_source_arn        = each.value.arn
  function_name           = aws_lambda_function.worker[each.key].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  dynamic "scaling_config" {
    for_each = var.workers[each.key].concurrency > 1 ? [1] : []
    content {
      maximum_concurrency = var.workers[each.key].concurrency
    }
  }
  lifecycle {
    precondition {
      condition     = each.value.visibility_timeout_seconds >= 6 * var.workers[each.key].timeout_seconds
      error_message = "Queue visibility must be at least six times the Lambda timeout."
    }
    precondition {
      condition     = try(jsondecode(each.value.redrive_policy).deadLetterTargetArn == each.value.dlq_arn, false)
      error_message = "The existing queue must have the supplied consumer DLQ configured."
    }
  }
}

resource "aws_sqs_queue" "dispatch_failures" {
  name                      = "${var.name_prefix}-dispatch-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role" "scheduler" {
  name = "${var.name_prefix}-notification-schedule"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" }
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}
resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = aws_lambda_function.worker["notification-dispatch"].arn },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.dispatch_failures.arn }
    ]
  })
}
resource "aws_scheduler_schedule" "dispatch" {
  name                = "${var.name_prefix}-notification-dispatch"
  schedule_expression = "rate(1 minute)"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.worker["notification-dispatch"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = "{}"
    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
    dead_letter_config { arn = aws_sqs_queue.dispatch_failures.arn }
  }
  depends_on = [aws_iam_role_policy.scheduler]
}

resource "aws_lambda_function_event_invoke_config" "dispatch" {
  function_name                = aws_lambda_function.worker["notification-dispatch"].function_name
  maximum_event_age_in_seconds = 300
  maximum_retry_attempts       = 0
  destination_config {
    on_failure { destination = aws_sqs_queue.dispatch_failures.arn }
  }
}

resource "aws_iam_role_policy" "dispatch_failure" {
  role = aws_iam_role.worker["notification-dispatch"].id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.dispatch_failures.arn }]
  })
}
