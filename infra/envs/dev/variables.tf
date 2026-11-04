variable "aws_account_id" {
  description = "Shared team AWS account ID. Guards against applying to the wrong account."
  type        = string
}

variable "aws_region" {
  description = "AWS region for this environment."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Project prefix used in resource names and tags."
  type        = string
  default     = "cs5224-team39"
}
