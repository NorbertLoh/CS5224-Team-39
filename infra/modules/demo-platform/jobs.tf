module "jobs" {
  count               = var.enable_workloads ? 1 : 0
  source              = "../background-jobs"
  name_prefix         = var.name_prefix
  environment         = "demo"
  subnet_ids          = [aws_subnet.private[0].id]
  security_group_ids  = [aws_security_group.workloads.id]
  document_bucket_arn = aws_s3_bucket.storage["documents"].arn
  ses_identity_arn    = aws_ses_email_identity.sender.arn
  alarm_action_arns   = [aws_sns_topic.operations.arn]
  workers = {
    document = {
      image_uri   = var.images["document-lambda"], config_secret_arn = aws_secretsmanager_secret.config["document"].arn,
      concurrency = 1, timeout_seconds = 120, memory_mb = 512,
      environment = { for k, v in local.public_env["document"] : k => v if k != "SERVICE_ENVIRONMENT" }
    }
    notification-intake = {
      image_uri   = var.images["notification-lambda"], config_secret_arn = aws_secretsmanager_secret.config["notification"].arn,
      concurrency = 1, timeout_seconds = 60, memory_mb = 256,
      environment = local.notification_environment
    }
    notification-dispatch = {
      image_uri   = var.images["notification-lambda"], config_secret_arn = aws_secretsmanager_secret.config["notification"].arn,
      concurrency = 1, timeout_seconds = 60, memory_mb = 256,
      environment = local.notification_environment
    }
  }
  consumer_queues = {
    document = {
      arn                        = aws_sqs_queue.consumer["document"].arn, dlq_arn = aws_sqs_queue.dlq["document"].arn,
      visibility_timeout_seconds = aws_sqs_queue.consumer["document"].visibility_timeout_seconds,
      redrive_policy             = aws_sqs_queue.consumer["document"].redrive_policy
    }
    notification-intake = {
      arn                        = aws_sqs_queue.consumer["notification"].arn, dlq_arn = aws_sqs_queue.dlq["notification"].arn,
      visibility_timeout_seconds = aws_sqs_queue.consumer["notification"].visibility_timeout_seconds,
      redrive_policy             = aws_sqs_queue.consumer["notification"].redrive_policy
    }
  }
  monitored_queues = merge(
    { for k, v in local.consumers : "${var.name_prefix}-${k}${v.fifo ? ".fifo" : ""}" => { is_dlq = false, max_age_seconds = 300 } },
    { for k, v in local.consumers : "${var.name_prefix}-${k}-dlq${v.fifo ? ".fifo" : ""}" => { is_dlq = true } },
    { "${var.name_prefix}-event-delivery-dlq" = { is_dlq = true } }
  )
  depends_on = [aws_route.private_egress, aws_ecr_repository_policy.lambda]
}
locals {
  notification_environment = merge({
    SERVICE_AWS_REGION     = "ap-southeast-1"
    SERVICE_IDENTITY_URL   = local.service_urls["identity"]
    SERVICE_SCHEDULING_URL = local.service_urls["scheduling"]
    SERVICE_DOCUMENT_URL   = local.service_urls["document"]
    SERVICE_FULFILMENT_URL = local.service_urls["fulfilment"]
    SERVICE_EMAIL_SENDER   = var.ses_sender
    SERVICE_APP_URL        = "https://${module.edge.domain_name}"
  }, lookup(var.service_environment, "notification", {}))
}
resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name          = "${var.name_prefix}-db-connections"
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.demo.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 50
  alarm_actions       = [aws_sns_topic.operations.arn]
  treat_missing_data  = "notBreaching"
}
resource "aws_cloudwatch_metric_alarm" "database_storage" {
  alarm_name          = "${var.name_prefix}-db-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.demo.id }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 2147483648
  alarm_actions       = [aws_sns_topic.operations.arn]
  treat_missing_data  = "notBreaching"
}
