output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "isolated_subnet_ids" {
  value = aws_subnet.isolated[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "service_security_group_id" {
  value = aws_security_group.service.id
}

output "database_security_group_id" {
  value = aws_security_group.database.id
}
