# The long-running stack: one Fargate task with the four backend containers
# sharing a network namespace, so the compose service names collapse to
# localhost:PORT (see docs/AWS_DEPLOYMENT_PLAN.md "Why a single ... task").

# Every process calls get_settings(), which requires API_KEY, GEMINI_API_KEY,
# and ANTHROPIC_API_KEY — so all four containers receive the same secrets.
locals {
  common_secrets = [
    { name = "DATABASE_URL", valueFrom = var.database_url_parameter_arn },
    { name = "GEMINI_API_KEY", valueFrom = aws_ssm_parameter.app["gemini_api_key"].arn },
    { name = "ANTHROPIC_API_KEY", valueFrom = aws_ssm_parameter.app["anthropic_api_key"].arn },
    { name = "API_KEY", valueFrom = aws_ssm_parameter.app["api_key"].arn },
  ]

  containers = [
    {
      name    = "api"
      image   = "${var.api_image_repo}:latest"
      port    = 8000
      command = ["uv", "run", "uvicorn", "reglens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
      env = [
        { name = "A2A_INGESTION_URL", value = "http://localhost:8001" },
        { name = "A2A_RISK_SCORER_URL", value = "http://localhost:8002" },
        { name = "ENVIRONMENT", value = "production" },
      ]
    },
    {
      name    = "langgraph"
      image   = "${var.langgraph_image_repo}:latest"
      port    = 8010
      command = ["uv", "run", "python", "-m", "reglens.supervisor.server"]
      env = [
        { name = "A2A_INGESTION_URL", value = "http://localhost:8001" },
        { name = "A2A_RISK_SCORER_URL", value = "http://localhost:8002" },
        { name = "ENVIRONMENT", value = "production" },
      ]
    },
    {
      name    = "adk-ingest"
      image   = "${var.adk_image_repo}:latest"
      port    = 8001
      command = ["uv", "run", "python", "-m", "reglens.agents.ingestion.server"]
      env = [
        { name = "ADK_AGENT_PORT", value = "8001" },
        { name = "ADK_AGENT_NAME", value = "document-ingestion" },
        { name = "ENVIRONMENT", value = "production" },
      ]
    },
    {
      name    = "adk-risk"
      image   = "${var.adk_image_repo}:latest"
      port    = 8002
      command = ["uv", "run", "python", "-m", "reglens.agents.risk_scorer.server"]
      env = [
        { name = "ADK_AGENT_PORT", value = "8002" },
        { name = "ADK_AGENT_NAME", value = "risk-scorer" },
        { name = "ENVIRONMENT", value = "production" },
      ]
    },
  ]
}

resource "aws_cloudwatch_log_group" "app" {
  for_each = toset([for c in local.containers : c.name])

  name              = "/reglens/${each.key}"
  retention_in_days = 14
}

# Runtime role for the app processes (distinct from the execution role, which
# only pulls images and reads secrets). Empty for now; X-Ray/OTel join here.
resource "aws_iam_role" "task" {
  name               = "reglens-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_ecs_task_definition" "app" {
  family                   = "reglens-app"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 2048
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    for c in local.containers : {
      name         = c.name
      image        = c.image
      essential    = true
      command      = c.command
      portMappings = [{ containerPort = c.port, protocol = "tcp" }]
      secrets      = local.common_secrets
      environment  = c.env

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app[c.name].name
          awslogs-region        = data.aws_region.current.region
          awslogs-stream-prefix = c.name
        }
      }
    }
  ])
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_ecs_service" "app" {
  name            = "reglens-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.service_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http, aws_ecs_cluster_capacity_providers.main]
}
