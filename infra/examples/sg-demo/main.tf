# Standalone example only. W01 PR #233 owns infra/envs/* and remote-state bootstrap.
# Wire the same module into that skeleton after coordinating its merge.
terraform {
  required_version = ">= 1.11"
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
    tags = { Project = var.name_prefix, Environment = "demo", ManagedBy = "Terraform" }
  }
}
module "demo" {
  source                  = "../../modules/demo-platform"
  name_prefix             = var.name_prefix
  origin_hostname         = var.origin_hostname
  hosted_zone_id          = var.hosted_zone_id
  origin_certificate_arn  = var.origin_certificate_arn
  ses_sender              = var.ses_sender
  budget_email            = var.budget_email
  monthly_budget_usd      = var.monthly_budget_usd
  images                  = var.images
  enable_workloads        = var.enable_workloads
  allow_destroy_demo_data = var.allow_destroy_demo_data
  service_environment     = var.service_environment
  service_secret_keys     = var.service_secret_keys
  # Explicit demo limits. Raising these requires an intentional reviewed edit.
  max_tasks        = 1
  allow_scale_out  = false
  cpu_architecture = "ARM64"
  redis_mode       = "sidecar"
  egress_mode      = "instance"
  enable_turn      = true
}
output "demo" { value = module.demo }
