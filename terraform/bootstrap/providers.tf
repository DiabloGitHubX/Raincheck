provider "aws" {
  region  = "eu-north-1"
  profile = "raincheck"

  default_tags {
    tags = {
      Project   = "Raincheck"
      ManagedBy = "Terraform"
      Purpose   = "Terraform Remote State"
    }
  }
}