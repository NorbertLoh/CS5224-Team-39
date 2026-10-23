output "environment" {
  value = local.environment
}

output "name_prefix" {
  description = "Prefix for resource names in this environment."
  value       = local.name_prefix
}
