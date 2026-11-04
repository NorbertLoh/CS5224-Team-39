data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  managed       = var.deployment_profile == "managed"
  environment   = local.managed ? "production" : "demo"
  log_retention = local.managed ? 14 : 3
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
  origin                 = var.domain_free ? "https://${module.edge.domain_name}/service" : "https://${local.managed ? coalesce(var.internal_origin_hostname, var.origin_hostname) : var.origin_hostname}"
  service_urls           = { for s in local.services : s => var.domain_free ? "${local.origin}/${local.paths[s]}" : "${local.origin}/api/v1/${local.paths[s]}" }
  task_services          = length(var.images) > 0 ? local.services : toset([])
  utility_needed         = var.egress_mode == "instance" || var.enable_turn
  legacy_utility         = local.utility_needed && (!local.managed || var.egress_mode == "instance")
}

resource "terraform_data" "guards" {
  lifecycle {
    precondition {
      condition     = data.aws_region.current.region == "ap-southeast-1"
      error_message = "This demo is restricted to Singapore (ap-southeast-1)."
    }
    precondition {
      condition     = (var.max_tasks == 1 && var.worker_max_tasks == 1 && var.turn_capacity.max == 1 && var.lambda_concurrency == 1 && var.redis_node_count == 1 && var.nat_gateway_count == 1 && !var.database_multi_az) || var.allow_scale_out
      error_message = "Demo capacity defaults are one. Raising replicas/concurrency or enabling HA requires allow_scale_out=true."
    }
    precondition {
      condition     = !local.managed || (var.egress_mode == "gateway" && var.redis_mode == "managed" && !var.allow_destroy_demo_data && (var.domain_free || (can(regex("^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$", var.internal_origin_hostname)) && var.internal_origin_hostname != var.origin_hostname)))
      error_message = "Managed profile requires NAT Gateway, ElastiCache, protected storage and either domain-free mode or a distinct internal origin DNS name."
    }
    precondition {
      condition     = !var.domain_free || (local.managed && var.egress_mode == "gateway" && var.origin_certificate_arn == null)
      error_message = "Domain-free mode requires the managed profile, NAT Gateway egress and no supplied origin certificate."
    }
    precondition {
      condition     = var.min_tasks <= var.max_tasks && var.worker_min_tasks <= var.worker_max_tasks
      error_message = "API and worker minima cannot exceed their maxima."
    }
    precondition {
      condition     = (!var.enable_workloads && length(var.images) == 0) || alltrue([for k in setunion(local.services, toset(["notification", "signalling", "document-lambda", "notification-lambda"]), var.redis_mode == "sidecar" ? toset(["redis"]) : toset([])) : contains(keys(var.images), k)])
      error_message = "Publish all API, signalling and Lambda images before enabling workloads."
    }
  }
}
