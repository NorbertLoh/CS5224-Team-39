data "aws_rds_engine_version" "postgres" {
  engine  = "postgres"
  version = "17"
}
resource "aws_db_subnet_group" "demo" {
  name       = var.name_prefix
  subnet_ids = aws_subnet.private[*].id
}
resource "aws_db_instance" "demo" {
  identifier                  = var.name_prefix
  engine                      = "postgres"
  engine_version              = data.aws_rds_engine_version.postgres.version
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "telelink"
  username                    = "telelink_admin"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.demo.name
  vpc_security_group_ids      = [aws_security_group.data.id]
  publicly_accessible         = false
  multi_az                    = false
  availability_zone           = data.aws_availability_zones.available.names[0]
  backup_retention_period     = 1
  auto_minor_version_upgrade  = true
  copy_tags_to_snapshot       = true
  deletion_protection         = false
  skip_final_snapshot         = true
  # Fixed 20 GiB: no automatic storage growth or paid replicas in the demo.
}
resource "aws_elasticache_subnet_group" "demo" {
  count      = var.redis_mode == "managed" ? 1 : 0
  name       = var.name_prefix
  subnet_ids = [aws_subnet.private[0].id]
}
resource "aws_elasticache_replication_group" "demo" {
  count                      = var.redis_mode == "managed" ? 1 : 0
  replication_group_id       = var.name_prefix
  description                = "Single demo cache node; PostgreSQL owns booking capacity"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false
  subnet_group_name          = aws_elasticache_subnet_group.demo[0].name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  snapshot_retention_limit   = 0
  # VPC SG isolation + TLS; no Terraform-managed plaintext Redis password.
}
resource "aws_secretsmanager_secret" "config" {
  for_each                = local.secret_owners
  name                    = "${var.name_prefix}/${each.key}/config"
  recovery_window_in_days = 7
  description             = "Operator-populated service Settings JSON; no values in Terraform"
}
resource "aws_s3_bucket" "storage" {
  for_each      = toset(["frontend", "documents", "logos"])
  bucket        = "${var.name_prefix}-${data.aws_caller_identity.current.account_id}-${each.key}"
  force_destroy = var.allow_destroy_demo_data
}
resource "aws_s3_bucket_public_access_block" "storage" {
  for_each                = aws_s3_bucket.storage
  bucket                  = each.value.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "private" {
  for_each = { for k, v in aws_s3_bucket.storage : k => v if k != "frontend" }
  bucket   = each.value.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [each.value.arn, "${each.value.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }]
  })
}
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  for_each = aws_s3_bucket.storage
  bucket   = each.value.id
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter { prefix = "" }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}
resource "aws_ecr_repository" "app" {
  for_each             = setunion(local.services, toset(["notification", "signalling", "document-lambda", "notification-lambda", "redis"]))
  name                 = "${var.name_prefix}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.allow_destroy_demo_data
  image_scanning_configuration { scan_on_push = false }
}
resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Keep three images for demo rollback", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }, action = { type = "expire" } }] })
}
resource "aws_ecr_repository_policy" "lambda" {
  for_each   = toset(["document-lambda", "notification-lambda"])
  repository = aws_ecr_repository.app[each.key].name
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Condition = { StringLike = { "aws:SourceArn" = "arn:aws:lambda:ap-southeast-1:${data.aws_caller_identity.current.account_id}:function:${var.name_prefix}-*" } } }]
  })
}
