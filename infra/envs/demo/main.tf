locals {
  environment = "demo"
  name_prefix = "${var.project}-${local.environment}"
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project     = var.project
      Environment = local.environment
      ManagedBy   = "terraform"
    }
  }
}

module "platform" {
  source              = "../../modules/demo-platform"
  name_prefix         = local.name_prefix
  deployment_profile  = "managed"
  domain_free         = true
  cpu_architecture    = "X86_64"
  egress_mode         = "gateway"
  redis_mode          = "managed"
  origin_hostname     = ""
  hosted_zone_id      = ""
  ses_sender          = var.ses_sender
  budget_email        = var.budget_email
  monthly_budget_usd  = var.monthly_budget_usd
  images              = var.images
  enable_workloads    = var.enable_workloads
  service_environment = var.service_environment
  service_secret_keys = var.service_secret_keys

  enable_demo_account_seed = true
}
