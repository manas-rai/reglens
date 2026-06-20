variable "api_image_repo" {
  description = "ECR repository URL for the api image (provides alembic + migrations)"
  type        = string
}

variable "langgraph_image_repo" {
  description = "ECR repository URL for the langgraph supervisor image"
  type        = string
}

variable "adk_image_repo" {
  description = "ECR repository URL for the shared ADK agent image"
  type        = string
}

variable "vpc_id" {
  description = "VPC the ALB target group lives in"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the ALB and the Fargate task"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group for the public ALB"
  type        = string
}

variable "service_security_group_id" {
  description = "Security group for the Fargate task"
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
