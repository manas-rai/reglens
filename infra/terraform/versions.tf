terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }

  # Bucket/key/region are supplied at init time so the account id never
  # lives in committed code:
  #   terraform init -backend-config=backend.hcl
  # (see backend.hcl.example; CI generates backend.hcl from repo variables)
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "reglens"
      ManagedBy = "terraform"
    }
  }
}
