# AWS Terraform Project

## Remote State Backend

- S3 bucket: megha-terraform-state
- DynamoDB table: terraform-locks
- Region: us-east-1

## Bootstrap

Run once to create the remote state backend:
```bash
cd terraform/bootstrap
terraform init
terraform apply
```
