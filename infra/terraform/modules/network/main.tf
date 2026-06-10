# VPC with two public subnets (ALB + the Fargate task, which gets a public
# IP so it can pull ECR images and call LLM APIs without a NAT) and two
# isolated subnets for RDS (no internet route in either direction). See
# docs/AWS_DEPLOYMENT_PLAN.md "Why no NAT".

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "reglens"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "reglens"
  }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "reglens-public-${local.azs[count.index]}"
  }
}

resource "aws_subnet" "isolated" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 10 + count.index)
  availability_zone = local.azs[count.index]

  tags = {
    Name = "reglens-isolated-${local.azs[count.index]}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "reglens-public"
  }
}

resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Isolated subnets keep the VPC's implicit main route table, which has no
# internet route — intentionally no route table resources for them.

# --- Security groups ----------------------------------------------------------
# Defined here (rather than in the fargate/rds modules) because they reference
# each other and both later phases need their ids.

resource "aws_security_group" "alb" {
  name        = "reglens-alb"
  description = "Public HTTP into the ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "To the service"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "reglens-alb"
  }
}

resource "aws_security_group" "service" {
  name        = "reglens-service"
  description = "Fargate task: API in from ALB only, all out (ECR pulls, LLM APIs)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "API from the ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "ECR pulls, Gemini/Anthropic APIs, RDS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "reglens-service"
  }
}

resource "aws_security_group" "database" {
  name        = "reglens-database"
  description = "Postgres from the Fargate task only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from the service"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.service.id]
  }

  tags = {
    Name = "reglens-database"
  }
}
