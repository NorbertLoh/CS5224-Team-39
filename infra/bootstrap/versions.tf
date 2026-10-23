terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Bootstrap creates the remote state bucket, so its own state stays local
  # (and gitignored). Run it once per AWS account.
}
