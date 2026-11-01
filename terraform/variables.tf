
variable "aws_region" {
  description = "AWS region where Raincheck infrastructure will be deployed."
  type        = string
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "AWS CLI profile used to authenticate Terraform."
  type        = string
  default     = "raincheck"
}

variable "project_name" {
  description = "Name of the project."
  type        = string
  default     = "raincheck"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "instance_type" {
  description = "EC2 instance type used by all Kubernetes nodes."
  type        = string
  default     = "t3.small"
}

variable "availability_zones" {
  description = "Availability Zones used by Raincheck networking."
  type        = list(string)
  default     = ["eu-north-1a"]

  validation {
    condition = (
      length(var.availability_zones) > 0 &&
      length(distinct(var.availability_zones)) == length(var.availability_zones)
    )
    error_message = "At least one Availability Zone must be specified, without duplicates."
  }
}



variable "allowed_ssh_cidr" {
  description = "Public IPv4 CIDR allowed to access Raincheck EC2 instances over SSH."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.allowed_ssh_cidr))
    error_message = "allowed_ssh_cidr must be a valid IPv4 CIDR block."
  }
}


variable "key_name" {
  description = "Name of the AWS EC2 key pair used by Raincheck instances."
  type        = string
  default     = "raincheck-key"
}

variable "ssh_public_key_path" {
  description = "Local path to the SSH public key registered with AWS."
  type        = string
  default     = "~/.ssh/raincheck.pem.pub"
}


# ---------------------------------------------------------------------------
# EC2 Root Volume Sizes
# ---------------------------------------------------------------------------

variable "master_volume_size" {
  description = "Root EBS volume size in GB for the K3s master node."
  type        = number
  default     = 15

  validation {
    condition     = var.master_volume_size >= 8
    error_message = "The master root volume must be at least 8 GB."
  }
}

variable "worker1_volume_size" {
  description = "Root EBS volume size in GB for the first worker node."
  type        = number
  default     = 15

  validation {
    condition     = var.worker1_volume_size >= 8
    error_message = "Worker 1 root volume must be at least 8 GB."
  }
}

variable "worker2_volume_size" {
  description = "Root EBS volume size in GB for the second worker node."
  type        = number
  default     = 20

  validation {
    condition     = var.worker2_volume_size >= 8
    error_message = "Worker 2 root volume must be at least 8 GB."
  }
}
