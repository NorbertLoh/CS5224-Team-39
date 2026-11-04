mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
}

variables {
  name_prefix            = "rf26-test"
  frontend_bucket_domain = "rf26-frontend.s3.ap-southeast-1.amazonaws.com"
  frontend_bucket_arn    = "arn:aws:s3:::rf26-frontend"
  api_domain             = "example.execute-api.ap-southeast-1.amazonaws.com"
  signalling_domain      = "signal.example.test"
}

run "private_service_and_signalling_origins" {
  command = plan
  variables {
    private_origins = {
      internal   = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:loadbalancer/app/internal/1234567890123456", domain = "internal.example.elb.amazonaws.com" }
      signalling = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:loadbalancer/app/signalling/1234567890123456", domain = "signalling.example.elb.amazonaws.com" }
    }
    service_source_ips = ["203.0.113.10"]
  }
  assert {
    condition     = length(aws_cloudfront_vpc_origin.private) == 2 && alltrue([for origin in aws_cloudfront_vpc_origin.private : origin.vpc_origin_endpoint_config[0].origin_protocol_policy == "http-only"])
    error_message = "Both private ALBs must use VPC origins rather than public HTTP origins."
  }
  assert {
    condition     = aws_cloudfront_distribution.app.ordered_cache_behavior[0].path_pattern == "/service/*" && aws_cloudfront_distribution.app.ordered_cache_behavior[0].viewer_protocol_policy == "https-only" && aws_cloudfront_distribution.app.ordered_cache_behavior[0].cache_policy_id == data.aws_cloudfront_cache_policy.disabled.id && strcontains(aws_cloudfront_function.service[0].code, "203.0.113.10") && strcontains(aws_cloudfront_function.service[0].code, "event.viewer.ip")
    error_message = "The uncached service route must enforce HTTPS and the actual NAT viewer address."
  }
}

run "reject_private_service_without_nat_allowlist" {
  command = plan
  variables {
    private_origins = { internal = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:loadbalancer/app/internal/1234567890123456", domain = "internal.example.elb.amazonaws.com" } }
  }
  expect_failures = [aws_cloudfront_function.service]
}

run "cache_only_public_reads" {
  command = plan
  assert {
    condition     = tolist([for b in aws_cloudfront_distribution.app.ordered_cache_behavior : b.path_pattern]) == tolist(["/api/v1/tenant/clinics", "/api/v1/tenant/clinics/by-slug/*", "/api/*", "/clinic-logos/*", "/peerjs/*"])
    error_message = "Public exceptions must precede the uncached API behavior."
  }
  assert {
    condition     = aws_cloudfront_cache_policy.public_clinics.min_ttl == 0 && aws_cloudfront_cache_policy.public_clinics.default_ttl == 0 && aws_cloudfront_cache_policy.public_clinics.max_ttl == 60
    error_message = "Cache only when the public endpoint opts in, for at most 60 seconds."
  }
  assert {
    condition     = alltrue([for b in aws_cloudfront_distribution.app.ordered_cache_behavior : toset(b.cached_methods) == toset(["GET", "HEAD"])])
    error_message = "Mutations must never be cached."
  }
  assert {
    condition     = alltrue([for e in aws_cloudfront_distribution.app.custom_error_response : e.response_code == null && e.error_caching_min_ttl == 0])
    error_message = "API errors must not be rewritten into successful SPA HTML."
  }
}
