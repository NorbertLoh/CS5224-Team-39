# Managed-service, single-replica composition. W01 owns remote-state bootstrap.
# Use an existing encrypted state bucket; do not deploy competing roots.
terraform {
  required_version = ">= 1.11"
  backend "s3" {}
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.71, < 7.0"
    }
  }
}
provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { Project = var.name_prefix, Environment = "production", ManagedBy = "Terraform" }
  }
}
module "platform" {
  source                    = "../../modules/demo-platform"
  name_prefix               = var.name_prefix
  deployment_profile        = "managed"
  deletion_protection       = var.deletion_protection
  final_snapshot_identifier = var.final_snapshot_identifier
  internal_origin_hostname  = var.internal_origin_hostname
  origin_hostname           = var.origin_hostname
  hosted_zone_id            = var.hosted_zone_id
  origin_certificate_arn    = var.origin_certificate_arn
  ses_sender                = var.ses_sender
  budget_email              = var.budget_email
  monthly_budget_usd        = var.monthly_budget_usd
  images                    = var.images
  enable_workloads          = var.enable_workloads
  allow_destroy_demo_data   = var.allow_destroy_demo_data
  service_environment       = var.service_environment
  service_secret_keys       = var.service_secret_keys
  # Configurable architecture; demo values live in capacity.tf/tfvars.
  min_tasks          = var.min_tasks
  max_tasks          = var.max_tasks
  worker_min_tasks   = var.worker_min_tasks
  worker_max_tasks   = var.worker_max_tasks
  allow_scale_out    = var.allow_scale_out
  lambda_concurrency = var.lambda_concurrency
  database_multi_az  = var.database_multi_az
  redis_node_count   = var.redis_node_count
  nat_gateway_count  = var.nat_gateway_count
  turn_capacity      = var.turn_capacity
  cpu_architecture   = "ARM64"
  redis_mode         = "managed"
  egress_mode        = "gateway"
  enable_turn        = true
}
output "platform" { value = module.platform }
