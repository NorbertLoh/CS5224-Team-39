resource "aws_acm_certificate" "origin" {
  count             = var.origin_certificate_arn == null ? 1 : 0
  domain_name       = var.origin_hostname
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}
resource "aws_route53_record" "certificate" {
  count   = var.origin_certificate_arn == null ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = tolist(aws_acm_certificate.origin[0].domain_validation_options)[0].resource_record_name
  type    = tolist(aws_acm_certificate.origin[0].domain_validation_options)[0].resource_record_type
  records = [tolist(aws_acm_certificate.origin[0].domain_validation_options)[0].resource_record_value]
  ttl     = 60
}
resource "aws_acm_certificate_validation" "origin" {
  count                   = var.origin_certificate_arn == null ? 1 : 0
  certificate_arn         = aws_acm_certificate.origin[0].arn
  validation_record_fqdns = [aws_route53_record.certificate[0].fqdn]
}
resource "aws_lb" "demo" {
  name                       = var.name_prefix
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb.id]
  idle_timeout               = 120
  enable_deletion_protection = false
}
resource "aws_route53_record" "origin" {
  zone_id = var.hosted_zone_id
  name    = var.origin_hostname
  type    = "A"
  alias {
    name                   = aws_lb.demo.dns_name
    zone_id                = aws_lb.demo.zone_id
    evaluate_target_health = true
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.demo.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.origin_certificate_arn != null ? var.origin_certificate_arn : aws_acm_certificate_validation.origin[0].certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      status_code  = "404"
      message_body = "{\"error\":\"not_found\"}"
    }
  }
}
resource "aws_lb_listener" "private" {
  load_balancer_arn = aws_lb.demo.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      status_code  = "404"
      message_body = "{\"error\":\"not_found\"}"
    }
  }
}
resource "aws_lb_target_group" "api" {
  for_each             = local.services
  name                 = "${var.name_prefix}-${replace(each.key, "clinical_records", "records")}"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.demo.id
  deregistration_delay = 10
  health_check {
    path                = "/health/ready"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
locals {
  listener_routes = merge(
    { for s in local.services : "public-${s}" => { service = s, listener = aws_lb_listener.https.arn } },
    { for s in local.services : "private-${s}" => { service = s, listener = aws_lb_listener.private.arn } }
  )
}
resource "aws_lb_listener_rule" "api" {
  for_each     = local.listener_routes
  listener_arn = each.value.listener
  priority     = index(sort(tolist(local.services)), each.value.service) + 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[each.value.service].arn
  }
  condition {
    path_pattern { values = ["/api/v1/${local.paths[each.value.service]}", "/api/v1/${local.paths[each.value.service]}/*"] }
  }
  dynamic "transform" {
    for_each = contains(local.preserve_prefix, each.value.service) ? [] : [1]
    content {
      type = "url-rewrite"
      url_rewrite_config {
        rewrite {
          regex   = "^/api/v1/${local.paths[each.value.service]}(/.*)?$"
          replace = "$1"
        }
      }
    }
  }
}
resource "aws_lb_target_group" "signalling" {
  name                 = "${var.name_prefix}-signal"
  port                 = 9000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.demo.id
  deregistration_delay = 10
  health_check { path = "/healthz" }
}
resource "aws_lb_listener_rule" "document_internal" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 5
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api["document"].arn
  }
  condition {
    path_pattern { values = ["/api/v1/document/internal/*"] }
  }
  transform {
    type = "url-rewrite"
    url_rewrite_config {
      rewrite {
        regex   = "^/api/v1/document(/internal/.*)$"
        replace = "$1"
      }
    }
  }
}
resource "aws_lb_listener_rule" "signalling" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 1
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.signalling.arn
  }
  condition {
    path_pattern { values = ["/peerjs", "/peerjs/*"] }
  }
}
resource "aws_apigatewayv2_api" "http" {
  name          = var.name_prefix
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_vpc_link" "demo" {
  name               = var.name_prefix
  subnet_ids         = [aws_subnet.private[0].id]
  security_group_ids = [aws_security_group.workloads.id]
}
resource "aws_apigatewayv2_integration" "alb" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = aws_lb_listener.private.arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.demo.id
  payload_format_version = "1.0"
  request_parameters     = { "overwrite:path" = "$request.path" }
}
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.http.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.spa.id]
    issuer   = local.issuer
  }
}
resource "aws_apigatewayv2_route" "protected" {
  for_each           = local.services
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "ANY /api/v1/${local.paths[each.key]}/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.alb.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  # Domain access-token signature/token_use/client/role/tenant checks remain in APIs.
}
resource "aws_apigatewayv2_route" "public" {
  for_each = toset([
    "GET /api/v1/tenant/clinics",
    "GET /api/v1/tenant/clinics/by-slug/{slug}",
    "GET /api/v1/tenant/clinics/{tenant_id}/doctors",
    "GET /api/v1/tenant/clinics/{tenant_id}/public-logo",
    "POST /api/v1/billing/webhooks/stripe"
  ])
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.alb.id}"
  authorization_type = "NONE"
}
resource "aws_apigatewayv2_route" "collection" {
  for_each           = local.services
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "ANY /api/v1/${local.paths[each.key]}"
  target             = "integrations/${aws_apigatewayv2_integration.alb.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}
resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/telelink/${var.name_prefix}/gateway"
  retention_in_days = 3
}
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway.arn
    format          = jsonencode({ requestId = "$context.requestId", routeKey = "$context.routeKey", status = "$context.status", integrationError = "$context.integrationErrorMessage" })
  }
}
resource "aws_cognito_user_pool" "users" {
  name                     = var.name_prefix
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}
resource "aws_cognito_user_pool_client" "spa" {
  name                                 = "${var.name_prefix}-spa"
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["https://${module.edge.domain_name}/auth/callback"]
  logout_urls                          = ["https://${module.edge.domain_name}/"]
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  access_token_validity                = 15
  id_token_validity                    = 15
  refresh_token_validity               = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
resource "aws_cognito_user_pool_domain" "login" {
  domain       = "${var.name_prefix}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.users.id
}
module "edge" {
  source                 = "../public-edge"
  name_prefix            = var.name_prefix
  frontend_bucket_domain = aws_s3_bucket.storage["frontend"].bucket_regional_domain_name
  frontend_bucket_arn    = aws_s3_bucket.storage["frontend"].arn
  api_domain             = trimprefix(aws_apigatewayv2_api.http.api_endpoint, "https://")
  signalling_domain      = var.origin_hostname
}
