variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "timer-cluster"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}
