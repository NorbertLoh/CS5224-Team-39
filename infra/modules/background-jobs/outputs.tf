output "function_arns" {
  value = { for name, worker in aws_lambda_function.worker : name => worker.arn }
}
output "dispatch_failure_queue_arn" {
  value = aws_sqs_queue.dispatch_failures.arn
}
