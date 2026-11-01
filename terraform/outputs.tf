
# ---------------------------------------------------------------------------
# VPC Outputs
# ---------------------------------------------------------------------------

output "vpc_id" {
  description = "ID of the Raincheck VPC."
  value       = aws_vpc.raincheck.id
}

output "public_subnet_id" {
  description = "ID of the Raincheck public subnet."
  value       = aws_subnet.public.id
}

# ---------------------------------------------------------------------------
# EC2 Public IP Outputs
# ---------------------------------------------------------------------------

output "master_public_ip" {
  description = "Public IPv4 address of the K3s master."
  value       = aws_instance.master.public_ip
}

output "worker1_public_ip" {
  description = "Public IPv4 address of Worker 1."
  value       = aws_instance.worker1.public_ip
}

output "worker2_public_ip" {
  description = "Public IPv4 address of Worker 2."
  value       = aws_instance.worker2.public_ip
}

# ---------------------------------------------------------------------------
# EC2 Private IP Outputs
# ---------------------------------------------------------------------------

output "master_private_ip" {
  description = "Private IPv4 address of the K3s master."
  value       = aws_instance.master.private_ip
}

output "worker1_private_ip" {
  description = "Private IPv4 address of Worker 1."
  value       = aws_instance.worker1.private_ip
}

output "worker2_private_ip" {
  description = "Private IPv4 address of Worker 2."
  value       = aws_instance.worker2.private_ip
}
