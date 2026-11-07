variable "enable_demo_reset" {
  description = "Explicit demo-only reset capability. Requires a populated seed secret and existing seeded platform login. Never enable for production."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_demo_reset || (var.domain_free && var.redis_mode == "managed" && var.enable_demo_account_seed)
    error_message = "Reset requires the domain-free demo, managed dedicated cache and seeded accounts."
  }
}

resource "aws_s3_bucket" "demo_reset" {
  count         = var.enable_demo_reset ? 1 : 0
  bucket        = "${var.name_prefix}-${data.aws_caller_identity.current.account_id}-reset"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "demo_reset" {
  count                   = var.enable_demo_reset ? 1 : 0
  bucket                  = aws_s3_bucket.demo_reset[0].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "demo_reset" {
  count  = var.enable_demo_reset ? 1 : 0
  bucket = aws_s3_bucket.demo_reset[0].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_versioning" "demo_reset" {
  count  = var.enable_demo_reset ? 1 : 0
  bucket = aws_s3_bucket.demo_reset[0].id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_policy" "demo_reset" {
  count  = var.enable_demo_reset ? 1 : 0
  bucket = aws_s3_bucket.demo_reset[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*",
      Resource  = [aws_s3_bucket.demo_reset[0].arn, "${aws_s3_bucket.demo_reset[0].arn}/*"],
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_secretsmanager_secret" "demo_reset" {
  count       = var.enable_demo_reset ? 1 : 0
  name        = "${var.name_prefix}/demo-reset/seed"
  description = "Operator-populated patient_phone and new_account_password for the requested RF07 demo seed."
}
resource "aws_iam_role" "demo_reset" {
  count = var.enable_demo_reset ? 1 : 0
  name  = "${var.name_prefix}-demo-reset"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" },
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
        ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:ap-southeast-1:${data.aws_caller_identity.current.account_id}:*" }
      }
    }]
  })
}
locals {
  reset_queue_arns = concat(
    [for q in aws_sqs_queue.consumer : q.arn], [for q in aws_sqs_queue.dlq : q.arn],
    [aws_sqs_queue.event_delivery_failures.arn, "arn:aws:sqs:ap-southeast-1:${data.aws_caller_identity.current.account_id}:${var.name_prefix}-dispatch-failures"]
  )
  reset_queue_urls = concat(
    [for q in aws_sqs_queue.consumer : q.url], [for q in aws_sqs_queue.dlq : q.url],
    [aws_sqs_queue.event_delivery_failures.url, "https://sqs.ap-southeast-1.amazonaws.com/${data.aws_caller_identity.current.account_id}/${var.name_prefix}-dispatch-failures"]
  )
}
resource "aws_iam_role_policy" "demo_reset" {
  count = var.enable_demo_reset ? 1 : 0
  role  = aws_iam_role.demo_reset[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.demo_reset[0].arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.demo_reset[0].arn}/reset/state.json" },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.demo_reset[0].arn, aws_db_instance.demo.master_user_secret[0].secret_arn] },
      { Effect = "Allow", Action = ["cognito-idp:AdminGetUser", "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword"], Resource = aws_cognito_user_pool.users.arn },
      { Effect = "Allow", Action = ["sqs:PurgeQueue", "sqs:GetQueueAttributes"], Resource = local.reset_queue_arns }
    ]
  })
}
resource "aws_ecs_task_definition" "demo_reset" {
  count                    = var.enable_demo_reset && length(var.images) > 0 ? 1 : 0
  family                   = "${var.name_prefix}-demo-reset"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution["document"].arn
  task_role_arn            = aws_iam_role.demo_reset[0].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([{
    name = "demo-reset", image = var.images["document"], essential = true,
    command = ["python", "-c", join("\n", [
      "import pathlib, sys",
      "pathlib.Path('/tmp/requested_seed.py').write_text(${jsonencode(file("${path.module}/../../../dev/demo_seed/requested_seed.py"))}, encoding='utf-8')",
      "sys.path.insert(0, '/tmp')",
      file("${path.module}/reset_demo.py")
    ])],
    environment = [{ name = "RESET_CONFIG", value = jsonencode({
      deployment    = "demo", account = data.aws_caller_identity.current.account_id,
      bucket        = aws_s3_bucket.demo_reset[0].id, pool = aws_cognito_user_pool.users.id,
      seed_secret   = aws_secretsmanager_secret.demo_reset[0].arn,
      master_secret = aws_db_instance.demo.master_user_secret[0].secret_arn,
      db_host       = aws_db_instance.demo.address,
      queues        = local.reset_queue_urls, redis_host = aws_elasticache_replication_group.demo[0].primary_endpoint_address
    }) }],
    logConfiguration = local.logs["document"]
  }])
  depends_on = [aws_iam_role_policy.demo_reset, aws_iam_role_policy.execution]
}
resource "aws_iam_role_policy" "request_demo_reset" {
  count = var.enable_demo_reset && length(var.images) > 0 ? 1 : 0
  role  = aws_iam_role.task["identity"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.demo_reset[0].arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.demo_reset[0].arn}/reset/state.json" },
      { Effect    = "Allow", Action = ["ecs:RunTask"], Resource = aws_ecs_task_definition.demo_reset[0].arn,
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.demo.arn } }
      },
      { Effect    = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.demo_reset[0].arn, aws_iam_role.execution["document"].arn],
        Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }
      }
    ]
  })
}
