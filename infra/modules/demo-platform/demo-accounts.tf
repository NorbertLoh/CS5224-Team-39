variable "enable_demo_account_seed" {
  description = "Allow the operator to seed synthetic accounts in this demo."
  type        = bool
  default     = false
}

resource "aws_secretsmanager_secret" "demo_logins" {
  count = var.enable_demo_account_seed ? 1 : 0
  name  = "${var.name_prefix}/demo-logins/${aws_cognito_user_pool.users.id}"
}

resource "aws_iam_role" "demo_seed" {
  count              = var.enable_demo_account_seed ? 1 : 0
  name               = "${var.name_prefix}-demo-seed"
  assume_role_policy = aws_iam_role.execution["document"].assume_role_policy
}

resource "aws_iam_role_policy" "demo_seed" {
  count = var.enable_demo_account_seed ? 1 : 0
  role  = aws_iam_role.demo_seed[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [
        aws_secretsmanager_secret.config["identity"].arn,
        aws_secretsmanager_secret.config["tenant"].arn,
        aws_secretsmanager_secret.demo_logins[0].arn,
      ] },
      { Effect = "Allow", Action = ["secretsmanager:PutSecretValue"], Resource = aws_secretsmanager_secret.demo_logins[0].arn },
      { Effect = "Allow", Action = [
        "cognito-idp:AdminGetUser", "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword",
        "cognito-idp:AdminUpdateUserAttributes",
      ], Resource = aws_cognito_user_pool.users.arn },
    ]
  })
}

resource "aws_ecs_task_definition" "demo_seed" {
  count                    = var.enable_demo_account_seed && length(var.images) > 0 ? 1 : 0
  family                   = "${var.name_prefix}-demo-seed"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution["document"].arn
  task_role_arn            = aws_iam_role.demo_seed[0].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([{
    name    = "demo-seed", image = var.images["document"], essential = true,
    command = ["python", "-c", file("${path.module}/demo_accounts.py")],
    environment = [
      { name = "DEMO_POOL", value = aws_cognito_user_pool.users.id },
      { name = "LOGIN_SECRET", value = aws_secretsmanager_secret.demo_logins[0].arn },
      { name = "IDENTITY_SECRET", value = aws_secretsmanager_secret.config["identity"].arn },
      { name = "TENANT_SECRET", value = aws_secretsmanager_secret.config["tenant"].arn },
    ],
    logConfiguration = local.logs["document"]
  }])
  depends_on = [aws_iam_role_policy.demo_seed, aws_iam_role_policy.execution]
}

# The demo rollout enables workloads only after all owning migrations exit zero.
resource "terraform_data" "demo_seed" {
  count            = var.enable_demo_account_seed && var.enable_workloads ? 1 : 0
  triggers_replace = aws_ecs_task_definition.demo_seed[0].arn

  provisioner "local-exec" {
    working_dir = abspath("${path.module}/../../..")
    command     = "node dev/release/seed-demo.mjs"
    environment = {
      TELELINK_DEMO_SEED = jsonencode({
        cluster_name               = aws_ecs_cluster.demo.name
        demo_seed_task             = aws_ecs_task_definition.demo_seed[0].arn
        demo_login_secret          = aws_secretsmanager_secret.demo_logins[0].name
        task_network_configuration = { awsvpcConfiguration = { subnets = local.workload_subnets, securityGroups = [aws_security_group.workloads.id], assignPublicIp = "DISABLED" } }
      })
    }
  }
}
