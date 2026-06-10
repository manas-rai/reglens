variable "api_image_repo" {
  description = "ECR repository URL for the api image (provides alembic + migrations)"
  type        = string
}

variable "database_url_parameter_arn" {
  description = "SSM SecureString ARN holding DATABASE_URL"
  type        = string
}

variable "secret_parameter_arns" {
  description = "All SSM parameter ARNs the execution role may read"
  type        = list(string)
}
