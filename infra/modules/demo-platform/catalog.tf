data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  services      = toset(["identity", "tenant", "scheduling", "consultation", "clinical_records", "billing", "document", "fulfilment"])
  secret_owners = setunion(local.services, toset(["notification", "signalling", "turn"]))
  workers = {
    identity         = {}
    tenant           = {}
    consultation     = {}
    scheduling       = { expiry = ["app.expire_holds"], consumer = ["app.payment_worker"], publisher = ["app.payment_worker", "--publish"], resolver = ["app.payment_worker", "--resolve"] }
    billing          = { expiry = ["app.expire_checkouts"], processor = ["app.payment_worker"], publisher = ["app.payment_worker", "--publish"] }
    clinical_records = { publisher = ["app.publish_events"] }
    document         = { publisher = ["app.publish_events"] }
    fulfilment       = { consumer = ["app.payment_worker"], submission = ["app.delivery_worker"], resolver = ["app.delivery_worker", "--resolve"], publisher = ["app.delivery_worker", "--publish"], tracking = ["app.tracking_worker"] }
  }
  paths = { for s in local.services : s => replace(s, "_", "-") }
  # These two APIs already include their full public prefix in their routers.
  preserve_prefix = toset(["document", "clinical_records"])
  memory          = { for s in local.services : s => contains(["scheduling", "billing", "fulfilment"], s) ? 1024 : 512 }
  app_secret_keys = {
    identity         = ["database_url", "cursor_secret", "scheduling_secret", "tenant_secret", "identity_secret", "records_secret", "fulfilment_secret", "consultation_secret", "notification_secret"]
    tenant           = ["database_url", "cursor_secret", "tenant_secret", "scheduling_secret", "identity_secret", "records_secret", "billing_secret", "fulfilment_secret"]
    scheduling       = ["database_url", "cursor_secret", "billing_secret", "consultation_secret", "notification_secret", "scheduling_secret", "operator_secret"]
    consultation     = ["database_url", "records_secret", "identity_secret", "scheduling_secret", "billing_secret", "signalling_secret", "turn_secret"]
    clinical_records = ["database_url", "cursor_secret", "fulfilment_secret", "document_secret", "consultation_secret", "identity_document_secret", "tenant_document_secret"]
    billing          = ["database_url", "cursor_secret", "scheduling_secret", "tenant_secret", "fulfilment_secret", "consultation_secret", "stripe_secret_key", "stripe_webhook_secret"]
    document         = ["database_url", "cursor_secret", "records_secret", "notification_secret"]
  }
  fulfilment_secret_keys = ["database_url", "cursor_secret", "records_secret", "tenant_secret", "profile_secret", "billing_secret", "notification_secret", "lalamove_api_key", "lalamove_api_secret", "delivery_locations_json"]
  issuer                 = "https://cognito-idp.ap-southeast-1.amazonaws.com/${aws_cognito_user_pool.users.id}"
  origin                 = "https://${var.origin_hostname}"
  service_urls           = { for s in local.services : s => "${local.origin}/api/v1/${local.paths[s]}" }
  task_services          = length(var.images) > 0 ? local.services : toset([])
  utility_needed         = var.egress_mode == "instance" || var.enable_turn
}

resource "terraform_data" "guards" {
  lifecycle {
    precondition {
      condition     = data.aws_region.current.region == "ap-southeast-1"
      error_message = "This demo is restricted to Singapore (ap-southeast-1)."
    }
    precondition {
      condition     = var.max_tasks == 1 || var.allow_scale_out
      error_message = "The demo is capped at one task; enable_scale_out budget approval must be explicit."
    }
    precondition {
      condition     = (!var.enable_workloads && length(var.images) == 0) || alltrue([for k in setunion(local.services, toset(["notification", "signalling", "document-lambda", "notification-lambda"]), var.redis_mode == "sidecar" ? toset(["redis"]) : toset([])) : contains(keys(var.images), k)])
      error_message = "Publish all API, signalling and Lambda images before enabling workloads."
    }
  }
}
