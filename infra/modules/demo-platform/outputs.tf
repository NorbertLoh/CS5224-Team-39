output "frontend_url" { value = "https://${module.edge.domain_name}" }
output "distribution_id" { value = module.edge.distribution_id }
output "cluster_name" { value = aws_ecs_cluster.demo.name }
output "repositories" { value = { for k, r in aws_ecr_repository.app : k => r.repository_url } }
output "config_secret_arns" { value = { for k, s in aws_secretsmanager_secret.config : k => s.arn } }
output "database_host" { value = aws_db_instance.demo.address }
output "database_master_secret_arn" { value = aws_db_instance.demo.master_user_secret[0].secret_arn }
output "redis_url" {
  value = var.redis_mode == "sidecar" ? "redis://127.0.0.1:6379/0" : "rediss://${aws_elasticache_replication_group.demo[0].primary_endpoint_address}:6379/0"
}
output "task_network_configuration" {
  value = { awsvpcConfiguration = { subnets = [aws_subnet.private[0].id], securityGroups = [aws_security_group.workloads.id], assignPublicIp = "DISABLED" } }
}
output "bootstrap_task" { value = try(aws_ecs_task_definition.bootstrap[0].arn, null) }
output "migration_tasks" { value = { for k, t in aws_ecs_task_definition.migration : k => t.arn } }
output "buckets" { value = { for k, b in aws_s3_bucket.storage : k => b.id } }
output "service_settings" {
  description = "Public environment settings only; credentials live in the separate secret containers."
  value       = merge(local.public_env, { notification = local.notification_environment })
}
output "frontend_environment" {
  value = {
    VITE_USE_AWS                    = "true"
    VITE_AWS_API_BASE_URL           = "https://${module.edge.domain_name}/api/v1"
    VITE_AWS_COGNITO_CLIENT_ID      = aws_cognito_user_pool_client.spa.id
    VITE_AWS_COGNITO_ISSUER         = local.issuer
    VITE_AWS_COGNITO_OAUTH_BASE_URL = "https://${aws_cognito_user_pool_domain.login.domain}.auth.ap-southeast-1.amazoncognito.com"
    VITE_AWS_COGNITO_API_URL        = "https://cognito-idp.ap-southeast-1.amazonaws.com/"
  }
}
output "stripe_webhook_url" { value = "https://${module.edge.domain_name}/api/v1/billing/webhooks/stripe" }
output "turn_urls" {
  value = var.enable_turn ? ["turn:${aws_eip.utility[0].public_ip}:3478?transport=udp", "turn:${aws_eip.utility[0].public_ip}:3478?transport=tcp"] : []
}
