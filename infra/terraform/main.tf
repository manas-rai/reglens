module "network" {
  source = "./modules/network"

  vpc_cidr = var.vpc_cidr
}

module "ecr" {
  source = "./modules/ecr"

  repositories = ["api", "langgraph", "adk"]
}

module "rds" {
  source = "./modules/rds"

  subnet_ids        = module.network.isolated_subnet_ids
  security_group_id = module.network.database_security_group_id
}

module "ecs" {
  source = "./modules/ecs"

  api_image_repo             = module.ecr.repository_urls["api"]
  database_url_parameter_arn = module.rds.database_url_parameter_arn
  secret_parameter_arns      = [module.rds.database_url_parameter_arn]
}
