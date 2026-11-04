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
variable "ses_sender" {
  description = "Real operator-owned email address, to be verified in SES before sending."
  type        = string
}
variable "budget_email" {
  description = "Operator email receiving the demo budget/SNS alerts."
  type        = string
}
variable "monthly_budget_usd" {
  type    = number
  default = 250
}
variable "images" {
  description = "Complete digest-pinned AMD64 release map; empty for foundation creation."
  type        = map(string)
  default     = {}
}
variable "enable_workloads" {
  description = "Enable only after images, secrets, DB bootstrap/migrations and providers are ready."
  type        = bool
  default     = false
}
variable "service_environment" {
  type    = map(map(string))
  default = {}
}
variable "service_secret_keys" {
  type    = map(set(string))
  default = {}
}
