# ECS cluster plus the one-shot migration task definition. The long-running
# service (api + langgraph + adk containers) joins this cluster in Phase C.

data "aws_region" "current" {}

resource "aws_ecs_cluster" "main" {
  name = "reglens"

  setting {
    name  = "containerInsights"
    value = "disabled" # paid feature; CloudWatch logs are enough for a demo
  }
}

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/reglens/migrate"
  retention_in_days = 14
}

# --- Task execution role (agent-side: pull image, write logs, read secrets) --

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "reglens-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    effect  = "Allow"
    actions = ["ssm:GetParameters"]
    resources = concat(
      var.secret_parameter_arns,
      [for p in aws_ssm_parameter.app : p.arn],
    )
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --- Migration task definition -----------------------------------------------

resource "aws_ecs_task_definition" "migrate" {
  family                   = "reglens-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = "${var.api_image_repo}:latest"
      essential = true
      command   = ["uv", "run", "alembic", "upgrade", "head"]

      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = var.database_url_parameter_arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.migrate.name
          awslogs-region        = data.aws_region.current.region
          awslogs-stream-prefix = "migrate"
        }
      }
    }
  ])
}
