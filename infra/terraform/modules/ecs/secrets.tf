# App secrets the containers read at startup. Created as SecureString
# placeholders; the real values are set out-of-band so they never live in
# Terraform code or state:
#
#   aws ssm put-parameter --name /reglens/gemini_api_key   --type SecureString --overwrite --value '...'
#   aws ssm put-parameter --name /reglens/anthropic_api_key --type SecureString --overwrite --value '...'
#   aws ssm put-parameter --name /reglens/api_key          --type SecureString --overwrite --value '...'

locals {
  app_secret_names = ["gemini_api_key", "anthropic_api_key", "api_key"]
}

resource "aws_ssm_parameter" "app" {
  for_each = toset(local.app_secret_names)

  name  = "/reglens/${each.key}"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
