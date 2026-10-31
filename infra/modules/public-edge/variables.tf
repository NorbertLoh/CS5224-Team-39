variable "name_prefix" { type = string }
variable "frontend_bucket_domain" {
  description = "Private S3 bucket regional REST endpoint, not a website endpoint."
  type        = string
}
variable "frontend_bucket_arn" { type = string }
variable "api_domain" {
  description = "Regional HTTP API hostname; existing API routes must accept /api/v1/... paths."
  type        = string
}
variable "signalling_domain" {
  description = "Existing reachable signalling origin DNS name with a matching TLS certificate; admission enforcement remains at the application."
  type        = string
}
variable "aliases" {
  type    = list(string)
  default = []
}
variable "certificate_arn" {
  description = "ACM certificate in us-east-1 when aliases are supplied."
  type        = string
  default     = null
}
