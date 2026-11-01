
# ---------------------------------------------------------------------------
# Ubuntu 22.04 LTS AMI
# ---------------------------------------------------------------------------

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}


# ---------------------------------------------------------------------------
# EC2 SSH Key Pair
# ---------------------------------------------------------------------------

resource "aws_key_pair" "raincheck" {
  key_name   = var.key_name
  public_key = file(pathexpand(var.ssh_public_key_path))

  tags = {
    Name = "${var.project_name}-${var.environment}-key"
  }
}


# ---------------------------------------------------------------------------
# K3s Master Node
# ---------------------------------------------------------------------------

resource "aws_instance" "master" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.raincheck.key_name
  subnet_id                   = aws_subnet.public.id
  private_ip                  = "10.0.1.10"
  associate_public_ip_address = true

  vpc_security_group_ids = [
    aws_security_group.raincheck.id
  ]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.master_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-master"
    Role = "master"
  }
}

# ---------------------------------------------------------------------------
# K3s Worker 1 - ArgoCD
# ---------------------------------------------------------------------------

resource "aws_instance" "worker1" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.raincheck.key_name
  subnet_id                   = aws_subnet.public.id
  private_ip                  = "10.0.1.11"
  associate_public_ip_address = true

  vpc_security_group_ids = [
    aws_security_group.raincheck.id
  ]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.worker1_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-worker1"
    Role = "worker"
  }
}

# ---------------------------------------------------------------------------
# K3s Worker 2 - Raincheck Application and Monitoring
# ---------------------------------------------------------------------------

resource "aws_instance" "worker2" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.raincheck.key_name
  subnet_id                   = aws_subnet.public.id
  private_ip                  = "10.0.1.12"
  associate_public_ip_address = true

  vpc_security_group_ids = [
    aws_security_group.raincheck.id
  ]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.worker2_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-worker2"
    Role = "worker"
  }
}
