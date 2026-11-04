locals {
  consumers = {
    scheduling   = { fifo = false, visibility = 60 }
    fulfilment   = { fifo = false, visibility = 60 }
    document     = { fifo = true, visibility = 720 }
    notification = { fifo = true, visibility = 360 }
  }
  event_patterns = {
    scheduling = { source = ["telelink.billing"], "detail-type" = ["consultation_payment_succeeded.v1"] }
    fulfilment = { source = ["telelink.billing"], "detail-type" = ["medication_payment_succeeded.v1"] }
    document   = { source = ["telelink.clinical-records"], "detail-type" = ["prescription_issued.v1", "medical_certificate_issued.v1"] }
    notification = { "$or" = [
      { source = ["telelink.scheduling"], "detail-type" = ["appointment_confirmed.v1"] },
      { source = ["telelink.document"], "detail-type" = ["document_ready.v1"] },
      { source = ["telelink.fulfilment"], "detail-type" = ["delivery_status_changed.v1"] }
    ] }
  }
}
resource "aws_cloudwatch_event_bus" "domain" { name = var.name_prefix }
resource "aws_sqs_queue" "dlq" {
  for_each                    = local.consumers
  name                        = "${var.name_prefix}-${each.key}-dlq${each.value.fifo ? ".fifo" : ""}"
  fifo_queue                  = each.value.fifo
  content_based_deduplication = each.value.fifo
  message_retention_seconds   = 1209600
  sqs_managed_sse_enabled     = true
}
resource "aws_sqs_queue" "consumer" {
  for_each                    = local.consumers
  name                        = "${var.name_prefix}-${each.key}${each.value.fifo ? ".fifo" : ""}"
  fifo_queue                  = each.value.fifo
  content_based_deduplication = each.value.fifo
  visibility_timeout_seconds  = each.value.visibility
  message_retention_seconds   = 345600
  receive_wait_time_seconds   = 20
  sqs_managed_sse_enabled     = true
  redrive_policy              = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn, maxReceiveCount = 3 })
}
resource "aws_sqs_queue_redrive_allow_policy" "consumer" {
  for_each             = local.consumers
  queue_url            = aws_sqs_queue.dlq[each.key].url
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.consumer[each.key].arn] })
}
resource "aws_sqs_queue" "event_delivery_failures" {
  name                      = "${var.name_prefix}-event-delivery-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_cloudwatch_event_rule" "consumer" {
  for_each       = local.consumers
  name           = "${var.name_prefix}-${each.key}"
  event_bus_name = aws_cloudwatch_event_bus.domain.name
  event_pattern  = jsonencode(local.event_patterns[each.key])
}
resource "aws_cloudwatch_event_target" "consumer" {
  for_each       = local.consumers
  rule           = aws_cloudwatch_event_rule.consumer[each.key].name
  event_bus_name = aws_cloudwatch_event_bus.domain.name
  arn            = aws_sqs_queue.consumer[each.key].arn
  target_id      = each.key
  dynamic "sqs_target" {
    for_each = each.value.fifo ? [1] : []
    content { message_group_id = "demo-single-worker" }
  }
  dead_letter_config { arn = aws_sqs_queue.event_delivery_failures.arn }
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 3
  }
  depends_on = [aws_sqs_queue_policy.consumer, aws_sqs_queue_policy.event_delivery]
}
resource "aws_sqs_queue_policy" "consumer" {
  for_each  = local.consumers
  queue_url = aws_sqs_queue.consumer[each.key].url
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.consumer[each.key].arn, Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.consumer[each.key].arn } } }] })
}
resource "aws_sqs_queue_policy" "event_delivery" {
  queue_url = aws_sqs_queue.event_delivery_failures.url
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.event_delivery_failures.arn, Condition = { ArnEquals = { "aws:SourceArn" = [for r in aws_cloudwatch_event_rule.consumer : r.arn] } } }] })
}
resource "aws_ses_email_identity" "sender" { email = var.ses_sender }
resource "aws_sns_topic" "operations" { name = "${var.name_prefix}-operations" }
resource "aws_sns_topic_subscription" "operations" {
  topic_arn = aws_sns_topic.operations.arn
  protocol  = "email"
  endpoint  = var.budget_email
}
resource "aws_budgets_budget" "demo" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_email]
    }
  }
}
