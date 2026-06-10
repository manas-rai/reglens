resource "aws_ecr_repository" "this" {
  for_each = toset(var.repositories)

  name = "reglens/${each.value}"

  image_scanning_configuration {
    scan_on_push = true
  }

  # Demo account: allow `terraform destroy` to remove repos with images in them.
  force_delete = true
}

# CI pushes :latest plus a :<git-sha> tag on every main merge; without a
# lifecycle policy the sha tags accumulate forever.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
