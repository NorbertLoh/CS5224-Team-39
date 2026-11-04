output "environment" {
  value = local.environment
}
output "platform" {
  description = "Public deployment configuration and resource identifiers; no service secret values."
  value       = module.platform
}

output "name_prefix" {
  description = "Prefix for resource names in this environment."
  value       = local.name_prefix
}
