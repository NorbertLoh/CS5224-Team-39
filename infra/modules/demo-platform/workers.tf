locals {
  worker_services = local.managed ? toset([for service in local.services : service if length(local.workers[service]) > 0]) : toset([])
  worker_containers = {
    for service in local.task_services : service => [for name, args in local.workers[service] : {
      name             = name
      image            = var.images[service]
      essential        = true
      environment      = [for key, value in local.public_env[service] : { name = key, value = value }]
      secrets          = local.ecs_secrets[service]
      command          = concat(service == "fulfilment" ? ["python", "-c", file("${path.module}/config_files.py")] : [], ["python", "-m"], args)
      logConfiguration = local.logs[service]
      stopTimeout      = 30
    }]
  }
}

# One worker group per owning service: API deployment/capacity is independent.
# Loops within a group share one task. Fulfilment's account poller stays singleton;
# other groups have configurable CPU scaling, subject to live DB/provider tests.
resource "aws_ecs_task_definition" "worker" {
  for_each                 = setintersection(local.task_services, local.worker_services)
  family                   = "${var.name_prefix}-${each.key}-workers"
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
  container_definitions = jsonencode(local.worker_containers[each.key])
  depends_on            = [terraform_data.guards, aws_iam_role_policy.execution, aws_iam_role_policy.task]
}

resource "aws_ecs_service" "worker" {
  for_each                           = var.enable_workloads ? local.worker_services : toset([])
  name                               = "${each.key}-workers"
  cluster                            = aws_ecs_cluster.demo.id
  task_definition                    = aws_ecs_task_definition.worker[each.key].arn
  desired_count                      = each.key == "fulfilment" ? 1 : var.worker_min_tasks
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = each.key != "fulfilment" && var.worker_min_tasks > 1 ? 50 : 0
  deployment_maximum_percent         = 100
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = local.workload_subnets
    security_groups  = [aws_security_group.workloads.id]
    assign_public_ip = false
  }
  depends_on = [aws_route.private_egress, aws_lb_listener_rule.api, aws_route53_record.internal_origin]
  lifecycle { ignore_changes = [desired_count] }
}

resource "aws_appautoscaling_target" "worker" {
  for_each           = var.enable_workloads ? local.worker_services : toset([])
  min_capacity       = each.key == "fulfilment" ? 1 : var.worker_min_tasks
  max_capacity       = each.key == "fulfilment" ? 1 : var.worker_max_tasks
  resource_id        = "service/${aws_ecs_cluster.demo.name}/${aws_ecs_service.worker[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
resource "aws_appautoscaling_policy" "worker_cpu" {
  for_each           = var.enable_workloads ? local.worker_services : toset([])
  name               = "${var.name_prefix}-${each.key}-worker-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.worker[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.worker[each.key].scalable_dimension
  service_namespace  = "ecs"
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 120
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
  }
}
