variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Supply the expected 12-digit AWS account ID."
  }
}
variable "name_prefix" {
  type    = string
  default = "telelink-demo"
}
variable "origin_hostname" { type = string }
variable "hosted_zone_id" { type = string }
variable "origin_certificate_arn" {
  type    = string
  default = null
}
variable "ses_sender" { type = string }
variable "budget_email" { type = string }
variable "monthly_budget_usd" {
  type    = number
  default = 100
}
variable "images" {
  type    = map(string)
  default = {}
}
variable "enable_workloads" {
  type    = bool
  default = false
}
variable "allow_destroy_demo_data" {
  type    = bool
  default = false
}
variable "service_environment" {
  type    = map(map(string))
  default = {}
}
variable "service_secret_keys" {
  type    = map(set(string))
  default = {}
}
