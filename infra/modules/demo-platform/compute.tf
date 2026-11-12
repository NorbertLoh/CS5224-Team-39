resource "aws_ecs_cluster" "demo" {
  name = var.name_prefix
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}
resource "aws_cloudwatch_log_group" "service" {
  for_each          = setunion(local.services, toset(["notification", "signalling", "bootstrap"]))
  name              = "/telelink/${var.name_prefix}/${each.key}"
  retention_in_days = local.log_retention
}
resource "aws_iam_role" "execution" {
  for_each           = setunion(local.services, toset(["notification", "signalling"]))
  name               = "${var.name_prefix}-${replace(each.key, "clinical_records", "records")}-exec"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }] })
}
resource "aws_iam_role_policy" "execution" {
  for_each = aws_iam_role.execution
  role     = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = concat([aws_ecr_repository.app[each.key].arn], each.key == "scheduling" ? [aws_ecr_repository.app["redis"].arn] : []) },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.service[each.key].arn}:*" },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.config[each.key].arn }
    ]
  })
}
resource "aws_iam_role" "task" {
  for_each           = setunion(local.services, toset(["notification", "signalling"]))
  name               = "${var.name_prefix}-${replace(each.key, "clinical_records", "records")}-task"
  assume_role_policy = aws_iam_role.execution[each.key].assume_role_policy
}
resource "aws_iam_role_policy" "task" {
  for_each = setsubtract(local.services, toset(["identity", "consultation"]))
  role     = aws_iam_role.task[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      contains(["scheduling", "billing", "clinical_records", "document", "fulfilment"], each.key) ? [{ Effect = "Allow", Action = ["events:PutEvents"], Resource = aws_cloudwatch_event_bus.domain.arn }] : [],
      contains(["scheduling", "fulfilment"], each.key) ? [{ Effect = "Allow", Action = ["sqs:GetQueueUrl", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.consumer[each.key].arn }] : [],
      each.key == "tenant" ? [
        { Effect = "Allow", Action = ["s3:GetBucketVersioning"], Resource = aws_s3_bucket.storage["logos"].arn },
        { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.storage["logos"].arn}/clinic-logos/*" }
      ] : [],
      each.key == "document" ? [
        { Effect = "Allow", Action = ["s3:GetBucketPublicAccessBlock"], Resource = aws_s3_bucket.storage["documents"].arn },
        { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.storage["documents"].arn}/*" }
      ] : []
    )
  })
}
locals {
  public_env = {
    for s in local.services : s => merge({
      SERVICE_NAME                       = s
      SERVICE_ENVIRONMENT                = local.environment
      SERVICE_HOST                       = "0.0.0.0"
      SERVICE_PORT                       = "8000"
      SERVICE_ROOT_PATH                  = contains(local.preserve_prefix, s) ? "" : "/api/v1/${local.paths[s]}"
      SERVICE_AWS_REGION                 = "ap-southeast-1"
      SERVICE_AUTH_ISSUER                = local.issuer
      SERVICE_AUTH_JWKS_URL              = "${local.issuer}/.well-known/jwks.json"
      SERVICE_AUTH_CLIENT_ID             = aws_cognito_user_pool_client.spa.id
      SERVICE_AUTH_REQUIRED_SCOPES       = "openid"
      SERVICE_AUTH_ALLOW_PASSWORD_TOKENS = "true"
      SERVICE_IDENTITY_URL               = local.service_urls["identity"]
      SERVICE_TENANT_URL                 = local.service_urls["tenant"]
      SERVICE_SCHEDULING_URL             = local.service_urls["scheduling"]
      SERVICE_BILLING_URL                = local.service_urls["billing"]
      SERVICE_RECORDS_URL                = local.service_urls["clinical_records"]
      SERVICE_FULFILMENT_URL             = local.service_urls["fulfilment"]
      SERVICE_EVENT_BUS_NAME             = aws_cloudwatch_event_bus.domain.name
      SERVICE_OUTBOX_METRICS             = "true"
      SERVICE_CORS_ORIGINS               = jsonencode(["https://${module.edge.domain_name}"])
      }, s == "identity" && var.enable_demo_reset && length(var.images) > 0 ? {
      SERVICE_DEMO_RESET_CONFIG = jsonencode({
        deployment = "demo", region = "ap-southeast-1",
        bucket     = aws_s3_bucket.demo_reset[0].id,
        cluster    = aws_ecs_cluster.demo.name,
        task       = aws_ecs_task_definition.demo_reset[0].arn,
        network    = { awsvpcConfiguration = { subnets = local.workload_subnets, securityGroups = [aws_security_group.workloads.id], assignPublicIp = "DISABLED" } }
      })
      } : {}, s == "scheduling" ? {
      SERVICE_REDIS_URL          = var.redis_mode == "sidecar" ? "redis://127.0.0.1:6379/0" : "rediss://${aws_elasticache_replication_group.demo[0].primary_endpoint_address}:6379/0"
      SERVICE_PAYMENT_QUEUE_NAME = aws_sqs_queue.consumer["scheduling"].name
      } : {}, s == "fulfilment" ? {
      SERVICE_PAYMENT_QUEUE_NAME = aws_sqs_queue.consumer["fulfilment"].name
      } : {}, s == "document" ? {
      SERVICE_DOCUMENT_BUCKET  = aws_s3_bucket.storage["documents"].id
      SERVICE_DOWNLOAD_VIA_API = "true"
      } : {}, s == "tenant" ? {
      SERVICE_LOGO_BUCKET          = aws_s3_bucket.storage["logos"].id
      SERVICE_LOGO_PUBLIC_BASE_URL = "https://${module.edge.domain_name}"
      } : {}, s == "consultation" ? {
      SERVICE_TURN_URLS             = jsonencode(local.turn_urls)
      SERVICE_SIGNALLING_MATCHMAKER = tostring(local.managed)
      SERVICE_SIGNALLING_NETWORKS   = jsonencode(aws_subnet.private[*].cidr_block)
      } : {}, s == "billing" ? {
      SERVICE_CHECKOUT_SUCCESS_URL = "https://${module.edge.domain_name}/payments/return"
      SERVICE_CHECKOUT_CANCEL_URL  = "https://${module.edge.domain_name}/appointments"
    } : {}, lookup(var.service_environment, s, {}))
  }
  ecs_secrets = {
    for s in local.services : s => [for field in setunion(toset(s == "fulfilment" ? local.fulfilment_secret_keys : local.app_secret_keys[s]), lookup(var.service_secret_keys, s, toset([]))) : {
      name      = "SERVICE_${upper(field)}"
      valueFrom = "${aws_secretsmanager_secret.config[s].arn}:${field}::"
    }]
  }
  logs = { for s, log in aws_cloudwatch_log_group.service : s => {
    logDriver = "awslogs"
    options   = { awslogs-group = log.name, awslogs-region = "ap-southeast-1", awslogs-stream-prefix = "ecs" }
  } }
}
resource "aws_ecs_task_definition" "api" {
  for_each                 = local.task_services
  family                   = "${var.name_prefix}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = tostring(local.memory[each.key])
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode(concat([
    {
      name             = "api"
      image            = var.images[each.key]
      essential        = true
      portMappings     = [{ containerPort = 8000, protocol = "tcp" }]
      environment      = [for k, v in local.public_env[each.key] : { name = k, value = v }]
      secrets          = local.ecs_secrets[each.key]
      logConfiguration = local.logs[each.key]
      command          = concat(each.key == "fulfilment" ? ["python", "-c", file("${path.module}/config_files.py")] : [], ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "64"])
      stopTimeout      = 30
    }
    ], local.managed ? [] : local.worker_containers[each.key], each.key == "scheduling" && var.redis_mode == "sidecar" ? [{
      name             = "redis"
      image            = var.images["redis"]
      essential        = true
      command          = ["redis-server", "--bind", "127.0.0.1", "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru", "--save", "", "--appendonly", "no"]
      logConfiguration = local.logs[each.key]
  }] : []))
  depends_on = [terraform_data.guards, aws_iam_role_policy.execution, aws_iam_role_policy.task]
}
resource "aws_ecs_service" "api" {
  for_each                           = var.enable_workloads ? local.services : toset([])
  name                               = each.key
  cluster                            = aws_ecs_cluster.demo.id
  task_definition                    = aws_ecs_task_definition.api[each.key].arn
  desired_count                      = local.api_minimum[each.key]
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = local.api_minimum[each.key] > 1 ? 50 : 0
  deployment_maximum_percent         = 100
  health_check_grace_period_seconds  = 180
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = local.workload_subnets
    security_groups  = [aws_security_group.workloads.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api[each.key].arn
    container_name   = "api"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener_rule.api, aws_route.private_egress, aws_route53_record.internal_origin]
  lifecycle { ignore_changes = [desired_count] }
}
resource "aws_appautoscaling_target" "api" {
  for_each           = var.enable_workloads ? local.services : toset([])
  min_capacity       = local.api_minimum[each.key]
  max_capacity       = local.api_maximum[each.key]
  resource_id        = "service/${aws_ecs_cluster.demo.name}/${aws_ecs_service.api[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
resource "aws_appautoscaling_policy" "cpu" {
  for_each           = var.enable_workloads ? local.services : toset([])
  name               = "${var.name_prefix}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.api[each.key].scalable_dimension
  service_namespace  = "ecs"
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 120
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
  }
}
resource "aws_ecs_task_definition" "signalling" {
  count                    = length(var.images) > 0 ? 1 : 0
  family                   = "${var.name_prefix}-signalling"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution["signalling"].arn
  task_role_arn            = aws_iam_role.task["signalling"].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([{
    name         = "signalling", image = var.images["signalling"], essential = true
    stopTimeout  = 120
    portMappings = [{ containerPort = 9000, protocol = "tcp" }]
    environment = [for k, v in {
      SIGNALLING_ENVIRONMENT             = "production", SIGNALLING_HOST = "0.0.0.0", SIGNALLING_PORT = "9000",
      SIGNALLING_ORIGINS                 = "https://${module.edge.domain_name}", CONSULTATION_URL = local.service_urls["consultation"]
      SIGNALLING_MATCHMAKER              = tostring(local.managed)
      SIGNALLING_REQUIRE_TASK_PROTECTION = tostring(local.managed)
      SIGNALLING_DRAIN_SECONDS           = "110"
    } : { name = k, value = v }]
    secrets          = [{ name = "SIGNALLING_SECRET", valueFrom = "${aws_secretsmanager_secret.config["signalling"].arn}:signalling_secret::" }]
    logConfiguration = local.logs["signalling"]
  }])
}
resource "aws_ecs_service" "signalling" {
  count                              = var.enable_workloads ? 1 : 0
  name                               = "signalling"
  cluster                            = aws_ecs_cluster.demo.id
  task_definition                    = aws_ecs_task_definition.signalling[0].arn
  desired_count                      = local.managed ? var.min_tasks : 1
  launch_type                        = "FARGATE"
  deployment_minimum_healthy_percent = local.managed && var.min_tasks > 1 ? 50 : 0
  deployment_maximum_percent         = 100
  network_configuration {
    subnets          = local.workload_subnets
    security_groups  = concat([aws_security_group.workloads.id], local.managed ? [aws_security_group.signalling_nodes[0].id] : [])
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.signalling.arn
    container_name   = "signalling"
    container_port   = 9000
  }
  depends_on = [aws_lb_listener_rule.signalling, aws_route.private_egress, aws_route53_record.internal_origin]
  lifecycle { ignore_changes = [desired_count] }
}

resource "aws_iam_role_policy" "signalling_protection" {
  count = local.managed ? 1 : 0
  role  = aws_iam_role.task["signalling"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow", Action = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"],
      Resource = "arn:aws:ecs:ap-southeast-1:${data.aws_caller_identity.current.account_id}:task/${aws_ecs_cluster.demo.name}/*"
    }]
  })
}

resource "aws_appautoscaling_target" "signalling" {
  count              = local.managed && var.enable_workloads ? 1 : 0
  min_capacity       = var.min_tasks
  max_capacity       = var.max_tasks
  resource_id        = "service/${aws_ecs_cluster.demo.name}/${aws_ecs_service.signalling[0].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "signalling" {
  count              = local.managed && var.enable_workloads ? 1 : 0
  name               = "${var.name_prefix}-signalling-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.signalling[0].resource_id
  scalable_dimension = aws_appautoscaling_target.signalling[0].scalable_dimension
  service_namespace  = "ecs"
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 180
    scale_out_cooldown = 60
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
  }
}
