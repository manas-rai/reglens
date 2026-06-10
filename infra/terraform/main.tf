module "network" {
  source = "./modules/network"

  vpc_cidr = var.vpc_cidr
}

module "ecr" {
  source = "./modules/ecr"

  repositories = ["api", "langgraph", "adk"]
}
