terraform {
  backend "s3" {
    bucket         = "megha-terraform-state"
    key            = "live/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
