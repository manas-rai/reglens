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

  api_image_repo       = module.ecr.repository_urls["api"]
  langgraph_image_repo = module.ecr.repository_urls["langgraph"]
  adk_image_repo       = module.ecr.repository_urls["adk"]

  database_url_parameter_arn = module.rds.database_url_parameter_arn
  secret_parameter_arns      = [module.rds.database_url_parameter_arn]

  vpc_id                    = module.network.vpc_id
  public_subnet_ids         = module.network.public_subnet_ids
  alb_security_group_id     = module.network.alb_security_group_id
  service_security_group_id = module.network.service_security_group_id
}
