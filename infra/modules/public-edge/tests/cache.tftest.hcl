mock_provider "aws" {}

variables {
  name_prefix            = "rf26-test"
  frontend_bucket_domain = "rf26-frontend.s3.ap-southeast-1.amazonaws.com"
  frontend_bucket_arn    = "arn:aws:s3:::rf26-frontend"
  api_domain             = "example.execute-api.ap-southeast-1.amazonaws.com"
  signalling_domain      = "signal.example.test"
}

run "cache_only_public_reads" {
  command = plan
  assert {
    condition     = tolist([for b in aws_cloudfront_distribution.app.ordered_cache_behavior : b.path_pattern]) == tolist(["/api/v1/tenant/clinics", "/api/v1/tenant/clinics/by-slug/*", "/api/*", "/peerjs/*"])
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
