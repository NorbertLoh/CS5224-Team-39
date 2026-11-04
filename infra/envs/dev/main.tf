locals {
  environment = "dev"
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

# Environment resources are added by later tasks (W02 network/ingress onwards),
# preferably as shared modules under infra/modules called from both environments.
