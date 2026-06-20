output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.main.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "migrate_task_definition_arn" {
  value = aws_ecs_task_definition.migrate.arn
}

output "migrate_log_group" {
  value = aws_cloudwatch_log_group.migrate.name
}

output "service_name" {
  value = aws_ecs_service.app.name
}

output "app_task_definition_arn" {
  value = aws_ecs_task_definition.app.arn
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}
