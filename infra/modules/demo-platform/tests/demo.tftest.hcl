mock_provider "aws" {
  mock_data "aws_region" { defaults = { region = "ap-southeast-1" } }
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_availability_zones" { defaults = { names = ["ap-southeast-1a", "ap-southeast-1b"] } }
  mock_data "aws_rds_engine_version" { defaults = { version = "17.6" } }
  mock_data "aws_ssm_parameter" { defaults = { value = "ami-0123456789abcdef0" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/demo" } }
  mock_resource "aws_db_instance" {
    defaults = { address = "demo.rds.amazonaws.com", master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:master-abcdef", kms_key_id = "test", secret_status = "active" }] }
  }
  mock_resource "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:config-abcdef" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::demo-storage", bucket_regional_domain_name = "demo-storage.s3.ap-southeast-1.amazonaws.com" } }
  mock_resource "aws_ecr_repository" { defaults = { arn = "arn:aws:ecr:ap-southeast-1:123456789012:repository/demo", repository_url = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/demo" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:ap-southeast-1:123456789012:log-group:demo" } }
  mock_resource "aws_sqs_queue" { defaults = { arn = "arn:aws:sqs:ap-southeast-1:123456789012:demo.fifo", url = "https://sqs.ap-southeast-1.amazonaws.com/123456789012/demo.fifo" } }
  mock_resource "aws_sns_topic" { defaults = { arn = "arn:aws:sns:ap-southeast-1:123456789012:demo" } }
  mock_resource "aws_cloudwatch_event_bus" { defaults = { arn = "arn:aws:events:ap-southeast-1:123456789012:event-bus/demo" } }
  mock_resource "aws_cloudwatch_event_rule" { defaults = { arn = "arn:aws:events:ap-southeast-1:123456789012:rule/demo" } }
  mock_resource "aws_lb" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:loadbalancer/app/demo/1234567890123456", dns_name = "demo.ap-southeast-1.elb.amazonaws.com", zone_id = "Z123456789" } }
  mock_resource "aws_lb_listener" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:listener/app/demo/1234567890123456/1234567890123456" } }
  mock_resource "aws_lb_target_group" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:targetgroup/demo/1234567890123456" } }
  mock_resource "aws_ecs_cluster" { defaults = { id = "arn:aws:ecs:ap-southeast-1:123456789012:cluster/demo" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:ap-southeast-1:123456789012:task-definition/demo:1" } }
  mock_resource "aws_lambda_function" { defaults = { arn = "arn:aws:lambda:ap-southeast-1:123456789012:function:demo" } }
  mock_resource "aws_ses_email_identity" { defaults = { arn = "arn:aws:ses:ap-southeast-1:123456789012:identity/demo@example.org" } }
  mock_resource "aws_eip" { defaults = { public_ip = "203.0.113.10" } }
}

variables {
  name_prefix            = "demo-test"
  origin_hostname        = "origin.demo.example.org"
  hosted_zone_id         = "Z123456789"
  origin_certificate_arn = "arn:aws:acm:ap-southeast-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
  ses_sender             = "demo@example.org"
  budget_email           = "owner@example.org"
}

run "cheap_foundation" {
  command = plan
  assert {
    condition     = aws_db_instance.demo.instance_class == "db.t4g.micro" && !aws_db_instance.demo.multi_az && aws_db_instance.demo.allocated_storage == 20
    error_message = "Use one encrypted small RDS instance and bounded storage."
  }
  assert {
    condition     = length(aws_instance.utility) == 1 && aws_instance.utility[0].instance_type == "t4g.nano" && length(aws_nat_gateway.demo) == 0 && length(aws_elasticache_replication_group.demo) == 0
    error_message = "Default demo must avoid managed NAT/cache hourly charges."
  }
  assert {
    condition     = length(aws_ecs_service.api) == 0 && length(aws_ecs_task_definition.api) == 0 && length(module.jobs) == 0
    error_message = "An empty foundation must not launch unconfigured workloads."
  }
  assert {
    condition     = aws_sqs_queue.consumer["document"].fifo_queue && aws_sqs_queue.consumer["notification"].fifo_queue && aws_cloudwatch_event_target.consumer["document"].sqs_target[0].message_group_id == "demo-single-worker"
    error_message = "Lambda concurrency-one requires one FIFO producer group."
  }
  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2 && !aws_db_instance.demo.publicly_accessible
    error_message = "Required two-AZ subnet groups must not expose the database."
  }
}

run "bounded_running_demo" {
  command = plan
  variables {
    enable_workloads = true
    images = {
      identity            = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/identity@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      tenant              = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/tenant@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      scheduling          = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/scheduling@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      consultation        = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/consultation@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      clinical_records    = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/records@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      billing             = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/billing@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      document            = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/document@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      fulfilment          = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/fulfilment@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      notification        = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/notification@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      signalling          = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/signalling@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      redis               = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/redis@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      document-lambda     = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/document-lambda@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      notification-lambda = "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/notification-lambda@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }
  assert {
    condition     = length(aws_ecs_service.api) == 8 && alltrue([for s in aws_ecs_service.api : s.desired_count == 1 && s.deployment_maximum_percent == 100]) && alltrue([for t in aws_appautoscaling_target.api : t.max_capacity == 1])
    error_message = "Every API must remain single-task, including during deployment."
  }
  assert {
    condition     = alltrue([for t in aws_ecs_task_definition.api : t.cpu == "256" && t.runtime_platform[0].cpu_architecture == "ARM64"]) && aws_ecs_service.signalling[0].desired_count == 1
    error_message = "Use small Graviton tasks and one signalling replica."
  }
  assert {
    condition     = length(aws_ecs_task_definition.migration) == 9 && length(aws_ecs_task_definition.bootstrap) == 1
    error_message = "Each schema needs an independent controlled migration task."
  }
  assert {
    condition     = local.public_env["scheduling"].SERVICE_REDIS_URL == "redis://127.0.0.1:6379/0" && length(local.workers["scheduling"]) == 4
    error_message = "The demo scheduling task must include its bounded local Redis mirror."
  }
  assert {
    condition     = alltrue([for limit in values(module.jobs[0].concurrency_limits) : limit == 1])
    error_message = "All three Lambda functions must have a hard concurrency ceiling of one."
  }
}

run "reject_unapproved_scale_out" {
  command = plan
  variables { max_tasks = 2 }
  expect_failures = [terraform_data.guards]
}

run "managed_single_nodes" {
  command = plan
  variables {
    egress_mode = "gateway"
    redis_mode  = "managed"
    enable_turn = false
  }
  assert {
    condition     = length(aws_nat_gateway.demo) == 1 && length(aws_instance.utility) == 0 && aws_elasticache_replication_group.demo[0].num_cache_clusters == 1 && !aws_elasticache_replication_group.demo[0].automatic_failover_enabled
    error_message = "Managed alternative must still have one NAT and no Redis replicas."
  }
}

run "request_origin_certificate" {
  command = plan
  variables { origin_certificate_arn = null }
  assert {
    condition     = length(aws_acm_certificate.origin) == 1 && length(aws_route53_record.certificate) == 1 && length(aws_acm_certificate_validation.origin) == 1
    error_message = "An owned Route53 zone must support automatic origin certificate validation."
  }
}

run "reject_other_region" {
  command = plan
  override_data {
    target = data.aws_region.current
    values = { region = "us-east-1" }
  }
  expect_failures = [terraform_data.guards]
}
