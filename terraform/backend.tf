terraform {
  backend "s3" {
    bucket       = "raincheck-tfstate-161072922899-eu-north-1"
    key          = "environments/dev/terraform.tfstate"
    region       = "eu-north-1"
    profile      = "raincheck"
    encrypt      = true
    use_lockfile = true
  }
}