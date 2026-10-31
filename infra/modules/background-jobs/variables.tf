variable "name_prefix" {
  type = string
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["development", "demo", "production"], var.environment)
    error_message = "Use an AWS environment name."
  }
}
variable "subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "Lambda workers require private subnets."
  }
}
variable "security_group_ids" {
  type = list(string)
}
variable "workers" {
  description = "Exactly document, notification-intake and notification-dispatch; images must use immutable digests. Secrets contain Settings field names."
  type = map(object({
    image_uri         = string
    config_secret_arn = string
    environment       = optional(map(string), {})
    concurrency       = number
    timeout_seconds   = number
    memory_mb         = optional(number, 512)
    kms_key_arns      = optional(list(string), [])
  }))
  validation {
    condition = (
      toset(keys(var.workers)) == toset(["document", "notification-intake", "notification-dispatch"]) &&
      alltrue([for w in values(var.workers) :
        can(regex("@sha256:[a-f0-9]{64}$", w.image_uri)) &&
        w.concurrency >= 2 && w.concurrency <= 20 && floor(w.concurrency) == w.concurrency &&
        w.timeout_seconds >= 30 && w.timeout_seconds <= 120 &&
        !contains(keys(w.environment), "SERVICE_ENVIRONMENT") &&
        !contains(keys(w.environment), "SERVICE_CONFIG_SECRET_ARN") &&
        !contains(keys(w.environment), "SERVICE_AWS_ENDPOINT_URL")
      ])
    )
    error_message = "Supply all three workers, digest-pinned images, integer concurrency 2-20 and timeouts 30-120s; reserved configuration keys cannot be overridden."
  }
}
variable "consumer_queues" {
  description = "Existing standard queues for document and notification-intake. The queue owner must configure the DLQ redrive policy and visibility timeout >= 6x Lambda timeout."
  type = map(object({
    arn                        = string
    dlq_arn                    = string
    visibility_timeout_seconds = number
    redrive_policy             = string
  }))
  validation {
    condition = (
      toset(keys(var.consumer_queues)) == toset(["document", "notification-intake"]) &&
      alltrue([for q in values(var.consumer_queues) : !endswith(q.arn, ".fifo")])
    )
    error_message = "Provide document and notification-intake standard queues."
  }
}
variable "document_bucket_arn" {
  type = string
}
variable "ses_identity_arn" {
  description = "Verified SES sender identity ARN in the worker region."
  type        = string
}
variable "alarm_action_arns" {
  description = "Existing SNS topic ARNs with confirmed subscriptions. Empty disables notifications, not alarms."
  type        = list(string)
}
variable "monitored_queues" {
  description = "All consumer queues, consumer DLQs and EventBridge delivery DLQs, keyed by queue name."
  type = map(object({
    is_dlq          = bool
    max_age_seconds = optional(number, 300)
  }))
}
variable "outbox_services" {
  type    = set(string)
  default = ["scheduling", "billing", "clinical_records", "document", "fulfilment"]
}
