output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "isolated_subnet_ids" {
  value = module.network.isolated_subnet_ids
}

output "ecr_repository_urls" {
  value = module.ecr.repository_urls
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "migrate_task_definition_arn" {
  value = module.ecs.migrate_task_definition_arn
}

output "api_url" {
  description = "Public HTTP endpoint for the API (ALB DNS name)"
  value       = "http://${module.ecs.alb_dns_name}"
}
