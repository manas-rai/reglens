# Single-AZ Postgres 18 (matches the local pgvector/pgvector:pg18 dev image)
# in the isolated subnets. Migration 001 runs CREATE EXTENSION vector as the
# master user, which RDS permits without any parameter-group changes.

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}

resource "random_password" "master" {
  length = 32
  # Alphanumeric only: the password is embedded in DATABASE_URL, and
  # URL-reserved characters would need percent-encoding everywhere.
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "reglens"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "main" {
  identifier = "reglens"

  engine         = "postgres"
  engine_version = "18.4"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "reglens"
  username = "reglens"
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 7
  auto_minor_version_upgrade = true

  # Demo account: allow clean `terraform destroy` without a snapshot dance.
  skip_final_snapshot = true
  deletion_protection = false
}

# The app and the migration task both consume a single DATABASE_URL env var
# (src/reglens/config.py), so store the fully composed URL rather than parts.
resource "aws_ssm_parameter" "database_url" {
  name  = "/reglens/database_url"
  type  = "SecureString"
  value = "postgresql+psycopg://${aws_db_instance.main.username}:${random_password.master.result}@${aws_db_instance.main.endpoint}/${aws_db_instance.main.db_name}"
}
