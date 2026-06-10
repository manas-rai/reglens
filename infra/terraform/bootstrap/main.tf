# One-time bootstrap, run locally with admin credentials:
#
#   cd infra/terraform/bootstrap
#   terraform init && terraform apply
#
# Creates the three things GitHub Actions needs before it can manage the
# rest of the stack: the Terraform state bucket, the GitHub OIDC identity
# provider, and the CI role. State for THIS stack stays local (it is tiny,
# changes ~never, and the bucket it would live in doesn't exist yet).

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "reglens"
      ManagedBy = "terraform-bootstrap"
    }
  }
}

variable "aws_region" {
  description = "Region for the state bucket and IAM resources"
  type        = string
  default     = "ap-south-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the CI role (owner/name)"
  type        = string
  default     = "manas-rai/reglens"
}

data "aws_caller_identity" "current" {}

locals {
  state_bucket = "reglens-tfstate-${data.aws_caller_identity.current.account_id}"
}

# --- Terraform state bucket ---------------------------------------------------

resource "aws_s3_bucket" "tfstate" {
  bucket = local.state_bucket
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- GitHub OIDC --------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # GitHub rotates its certs; AWS validates the issuer against this root CA
  # thumbprint but no longer hard-fails on it. Keeping the well-known value.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

# Demo tradeoff: one broad CI role instead of separate scoped roles for
# image-push vs terraform-apply. Terraform manages VPC/ECR/RDS/ECS/IAM/S3/
# CloudFront across phases, so a least-privilege policy would be large and
# brittle while the stack is still growing. Revisit before any production use.
resource "aws_iam_role" "github_actions" {
  name               = "reglens-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

resource "aws_iam_role_policy_attachment" "github_actions_admin" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# --- Outputs ------------------------------------------------------------------

output "state_bucket" {
  value = aws_s3_bucket.tfstate.bucket
}

output "ci_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "account_id" {
  description = "Set this as the AWS_ACCOUNT_ID repository variable in GitHub"
  value       = data.aws_caller_identity.current.account_id
}
