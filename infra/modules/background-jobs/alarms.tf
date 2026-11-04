locals {
  queues = merge(var.monitored_queues, { ("${var.name_prefix}-dispatch-failures") = { is_dlq = true, max_age_seconds = 300 } })
}
resource "aws_cloudwatch_metric_alarm" "queue" {
  for_each            = local.queues
  alarm_name          = "${var.name_prefix}-${each.key}-backlog"
  namespace           = "AWS/SQS"
  metric_name         = each.value.is_dlq ? "ApproximateNumberOfMessagesVisible" : "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = each.key }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = each.value.is_dlq ? 0 : each.value.max_age_seconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_action_arns
  ok_actions          = var.alarm_action_arns
}
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each            = var.workers
  alarm_name          = "${var.name_prefix}-${each.key}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.worker[each.key].function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_action_arns
}
resource "aws_cloudwatch_metric_alarm" "outbox_age" {
  for_each            = var.outbox_services
  alarm_name          = "${var.name_prefix}-${each.key}-outbox-age"
  namespace           = "TeleLink/Outbox"
  metric_name         = "OldestPendingAge"
  dimensions          = { Service = each.key, Environment = var.environment }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 300
  treat_missing_data  = "breaching"
  alarm_actions       = var.alarm_action_arns
}
