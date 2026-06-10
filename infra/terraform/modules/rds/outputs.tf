output "endpoint" {
  value = aws_db_instance.main.endpoint
}

output "database_url_parameter_arn" {
  value = aws_ssm_parameter.database_url.arn
}

output "database_url_parameter_name" {
  value = aws_ssm_parameter.database_url.name
}
