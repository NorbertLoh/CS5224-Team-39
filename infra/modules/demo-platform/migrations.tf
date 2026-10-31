resource "aws_iam_role" "bootstrap" {
  name               = "${var.name_prefix}-bootstrap"
  assume_role_policy = aws_iam_role.execution["document"].assume_role_policy
}
resource "aws_iam_role_policy" "bootstrap" {
  role = aws_iam_role.bootstrap.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = concat([aws_db_instance.demo.master_user_secret[0].secret_arn], [for s in setunion(local.services, toset(["notification"])) : aws_secretsmanager_secret.config[s].arn]) },
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = aws_ecr_repository.app["document"].arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.service["bootstrap"].arn}:*" }
    ]
  })
}
resource "aws_ecs_task_definition" "bootstrap" {
  count                    = length(var.images) > 0 ? 1 : 0
  family                   = "${var.name_prefix}-bootstrap"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.bootstrap.arn
  task_role_arn            = aws_iam_role.bootstrap.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([{
    name    = "bootstrap", image = var.images["document"], essential = true,
    command = ["python", "-c", file("${path.module}/bootstrap_database.py")],
    environment = [
      { name = "DB_HOST", value = aws_db_instance.demo.address },
      { name = "DB_MASTER_SECRET_ARN", value = aws_db_instance.demo.master_user_secret[0].secret_arn },
      { name = "SERVICE_CONFIG_ARNS", value = jsonencode({ for s in setunion(local.services, toset(["notification"])) : s => aws_secretsmanager_secret.config[s].arn }) }
    ],
    logConfiguration = local.logs["bootstrap"]
  }])
}
resource "aws_ecs_task_definition" "migration" {
  for_each                 = length(var.images) > 0 ? setunion(local.services, toset(["notification"])) : toset([])
  family                   = "${var.name_prefix}-${each.key}-migration"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([{
    name             = "migration", image = var.images[each.key], essential = true,
    entryPoint       = ["python", "-m", "alembic"], command = ["upgrade", "head"],
    environment      = [{ name = "SERVICE_ENVIRONMENT", value = "demo" }],
    secrets          = [{ name = "SERVICE_DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.config[each.key].arn}:database_url::" }],
    logConfiguration = local.logs[each.key]
  }])
}
