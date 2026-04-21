output "bucket_name" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.state.bucket
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for state locking"
  value       = aws_dynamodb_table.locks.name
}

output "region" {
  description = "AWS region"
  value       = var.region
}
