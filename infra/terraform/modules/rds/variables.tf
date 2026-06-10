variable "subnet_ids" {
  description = "Isolated subnet ids for the DB subnet group"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group attached to the DB instance"
  type        = string
}
