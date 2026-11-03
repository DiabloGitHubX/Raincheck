
# ---------------------------------------------------------------------------
# Raincheck Cluster Security Group
# ---------------------------------------------------------------------------

resource "aws_security_group" "raincheck" {
  name        = "${var.project_name}-${var.environment}-sg"
  description = "Security group for Raincheck Kubernetes cluster"
  vpc_id      = aws_vpc.raincheck.id

  # SSH access from the administrator's public IP only.
  ingress {
    description = "SSH access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Allow communication between members of the Raincheck cluster.
  ingress {
    description = "Internal cluster communication"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # Allow outbound traffic for package downloads, container images,
  # external APIs, and other required connections.
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-sg"
  }
}
