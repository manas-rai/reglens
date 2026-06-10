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
