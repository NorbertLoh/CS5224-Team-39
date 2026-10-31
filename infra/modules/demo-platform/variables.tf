variable "name_prefix" {
  type    = string
  default = "telelink-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name_prefix))
    error_message = "Use a 3-20 character lowercase resource prefix."
  }
}
variable "enable_workloads" {
  description = "Enable only after ECR images, service JSON secrets, database bootstrap/migrations and external sandbox credentials are ready. False does not stop infrastructure billing."
  type        = bool
  default     = false
}
variable "images" {
  description = "Digest-pinned images for eight APIs, signalling, notification-lambda and document-lambda. ECS images must match cpu_architecture; Lambda images remain x86_64."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for image in values(var.images) : can(regex("@sha256:[a-f0-9]{64}$", image))])
    error_message = "Use immutable image digests."
  }
}
variable "cpu_architecture" {
  type    = string
  default = "ARM64"
  validation {
    condition     = contains(["ARM64", "X86_64"], var.cpu_architecture)
    error_message = "Choose a compatible Linux architecture."
  }
}
variable "origin_hostname" {
  description = "Owned origin DNS name, for example origin.demo.example.org."
  type        = string
}
variable "hosted_zone_id" { type = string }
variable "origin_certificate_arn" {
  description = "Optional existing Singapore ACM certificate. Null requests a DNS-validated certificate using the supplied owned Route53 zone."
  type        = string
  default     = null
}
variable "ses_sender" {
  description = "Owned sender mailbox; AWS verification email must be confirmed outside Terraform."
  type        = string
}
variable "budget_email" { type = string }
variable "monthly_budget_usd" {
  type    = number
  default = 100
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "Budget must be positive; it is an alert, not a spending cap."
  }
}
variable "egress_mode" {
  description = "instance is cheapest for this small demo; gateway is managed but has a larger hourly baseline. Both use one AZ."
  type        = string
  default     = "instance"
  validation {
    condition     = contains(["instance", "gateway"], var.egress_mode)
    error_message = "Choose instance or gateway."
  }
}
variable "enable_turn" {
  description = "One coturn process on the shared public utility/NAT instance."
  type        = bool
  default     = true
}
variable "redis_mode" {
  description = "A localhost Redis sidecar costs no extra task and only mirrors durable holds. managed provisions one TLS ElastiCache node."
  type        = string
  default     = "sidecar"
  validation {
    condition     = contains(["sidecar", "managed"], var.redis_mode)
    error_message = "Choose sidecar or managed."
  }
}
variable "allow_scale_out" {
  description = "Explicit budget opt-in needed before raising max_tasks above one."
  type        = bool
  default     = false
}
variable "max_tasks" {
  type    = number
  default = 1
  validation {
    condition     = var.max_tasks >= 1 && var.max_tasks <= 5 && floor(var.max_tasks) == var.max_tasks
    error_message = "Use an integer maximum of 1-5, plus allow_scale_out to exceed one."
  }
}
variable "service_environment" {
  description = "Additional public SERVICE_* settings per service; never put credentials here."
  type        = map(map(string))
  default     = {}
  validation {
    condition     = alltrue(flatten([for env in values(var.service_environment) : [for key in keys(env) : !contains(["SERVICE_ENVIRONMENT", "SERVICE_AWS_ENDPOINT_URL", "SERVICE_CONFIG_SECRET_ARN"], key)]]))
    error_message = "Do not override the demo environment or enable local emulator endpoints."
  }
}
variable "service_secret_keys" {
  description = "Extra JSON Settings field names to inject from each service's own Secrets Manager configuration (for example stripe_secret_key). Never supply their values to Terraform."
  type        = map(set(string))
  default     = {}
}
variable "allow_destroy_demo_data" {
  description = "Allows deleting nonempty synthetic-data buckets during teardown. Leave false until data has been explicitly reviewed."
  type        = bool
  default     = false
}
