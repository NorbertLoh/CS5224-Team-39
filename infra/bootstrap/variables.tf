variable "aws_account_id" {
  description = "Shared team AWS account ID. Guards against applying to the wrong account."
  type        = string
}

variable "aws_region" {
  description = "Region for the state bucket and all environments."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Project prefix used in resource names and tags."
  type        = string
  default     = "cs5224-team39"
}

variable "monthly_budget_usd" {
  description = "Monthly account cost budget in USD. Alerts fire at 50%, 80% and 100%."
  type        = number
}

variable "budget_alert_emails" {
  description = "Email addresses that receive budget alerts."
  type        = list(string)

  validation {
    condition     = length(var.budget_alert_emails) > 0
    error_message = "Provide at least one budget alert email."
  }
}
