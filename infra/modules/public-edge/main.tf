data "aws_cloudfront_cache_policy" "disabled" { name = "Managed-CachingDisabled" }
data "aws_cloudfront_cache_policy" "assets" { name = "Managed-CachingOptimized" }
data "aws_cloudfront_origin_request_policy" "api" { name = "Managed-AllViewerExceptHostHeader" }

resource "aws_cloudfront_cache_policy" "public_clinics" {
  name        = "${var.name_prefix}-public-clinics"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 60
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings { items = ["limit", "cursor"] }
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name_prefix}-frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa" {
  name    = "${var.name_prefix}-spa"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite frontend navigation only; attached solely to the default behavior."
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      var path = request.uri;
      if ((request.method === 'GET' || request.method === 'HEAD') &&
          path !== '/api' && path.indexOf('/api/') !== 0 &&
          path !== '/peerjs' && path.indexOf('/peerjs/') !== 0 &&
          path.split('/').pop().indexOf('.') === -1) {
        request.uri = '/index.html';
      }
      return request;
    }
  JS
}
resource "aws_cloudfront_function" "logo" {
  name    = "${var.name_prefix}-public-logo"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      var match = request.uri.match(/^\/clinic-logos\/([0-9a-fA-F-]{36})\/logo\.png$/);
      if (!match || (request.method !== 'GET' && request.method !== 'HEAD')) {
        return {statusCode: 404, statusDescription: 'Not Found', headers: {'cache-control': {value: 'no-store'}}};
      }
      request.uri = '/api/v1/tenant/clinics/' + match[1] + '/public-logo';
      return request;
    }
  JS
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = var.aliases
  price_class         = "PriceClass_All"

  origin {
    domain_name              = var.frontend_bucket_domain
    origin_id                = "frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
    s3_origin_config { origin_access_identity = "" }
  }
  dynamic "origin" {
    for_each = { api = var.api_domain, signalling = var.signalling_domain }
    content {
      domain_name = origin.value
      origin_id   = origin.key
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  # Order matters: these exact public read patterns precede the general API rule.
  dynamic "ordered_cache_behavior" {
    for_each = ["/api/v1/tenant/clinics", "/api/v1/tenant/clinics/by-slug/*"]
    content {
      path_pattern           = ordered_cache_behavior.value
      target_origin_id       = "api"
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods         = ["GET", "HEAD"]
      cache_policy_id        = aws_cloudfront_cache_policy.public_clinics.id
      # POST /clinics shares this path: forward authentication for mutations.
      # GET responses here must remain identical for every viewer.
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
      compress                 = true
    }
  }
  dynamic "ordered_cache_behavior" {
    for_each = { "/api/*" = "api", "/clinic-logos/*" = "api", "/peerjs/*" = "signalling" }
    content {
      path_pattern             = ordered_cache_behavior.key
      target_origin_id         = ordered_cache_behavior.value
      viewer_protocol_policy   = "redirect-to-https"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
      compress                 = true
      dynamic "function_association" {
        for_each = ordered_cache_behavior.key == "/clinic-logos/*" ? [1] : []
        content {
          event_type   = "viewer-request"
          function_arn = aws_cloudfront_function.logo.arn
        }
      }
    }
  }
  default_cache_behavior {
    target_origin_id       = "frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.assets.id
    compress               = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }
  dynamic "custom_error_response" {
    for_each = toset([400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504])
    content {
      error_code            = custom_error_response.value
      error_caching_min_ttl = 0
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    cloudfront_default_certificate = length(var.aliases) == 0
    acm_certificate_arn            = var.certificate_arn
    ssl_support_method             = length(var.aliases) > 0 ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }
  lifecycle {
    precondition {
      condition     = length(var.aliases) == 0 || var.certificate_arn != null
      error_message = "Custom aliases require an ACM certificate in us-east-1."
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = split(":", var.frontend_bucket_arn)[5]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Principal = { Service = "cloudfront.amazonaws.com" }, Action = "s3:GetObject"
      Resource  = "${var.frontend_bucket_arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app.arn } }
      }, {
      Effect    = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [var.frontend_bucket_arn, "${var.frontend_bucket_arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
