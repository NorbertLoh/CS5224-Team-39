output "state_bucket" {
  description = "Put this value in each environment's backend.hcl."
  value       = aws_s3_bucket.state.bucket
}
