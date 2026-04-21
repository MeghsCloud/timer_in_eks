# Timer App on EKS — Runbook

## Overview
A real-time shared timer app built with Python FastAPI + WebSockets, deployed on AWS EKS using Terraform.

**Live URL:** `http://3.82.136.197:30080`  
**GitHub:** https://github.com/MeghsCloud/timer_in_eks

---

## Architecture
```
Internet → NodePort (30080) → EKS Node → Pod (timer-app) → FastAPI WebSocket
```

- **App:** Python FastAPI + WebSockets (real-time synced timer)
- **Container:** Docker image on ECR
- **Orchestration:** EKS (Kubernetes 1.32)
- **Infrastructure:** Terraform
- **State Backend:** S3 + DynamoDB

---

## Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform installed (`brew install hashicorp/tap/terraform`)
- kubectl installed (`brew install kubectl`)
- Docker Desktop running
- Git configured

---

## Step 1 — Bootstrap Remote State

Creates S3 bucket and DynamoDB table for Terraform state.

```bash
cd terraform/bootstrap
terraform init
terraform apply -auto-approve
```

**Resources created:**
- S3 bucket: `megha-terraform-state`
- DynamoDB table: `terraform-locks`

---

## Step 2 — Deploy Infrastructure

Creates VPC, EKS cluster, and node group.

```bash
cd terraform/live
terraform init
terraform apply -auto-approve
```

---

### How the VPC was created

A VPC (Virtual Private Cloud) is an isolated network in AWS where all resources live.

```hcl
resource "aws_vpc" "this" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
```

- CIDR `10.0.0.0/16` gives 65,536 private IP addresses
- DNS support enabled so pods can resolve hostnames inside the cluster

---

### How the Subnets were created

We created **2 public subnets** across 2 different Availability Zones. EKS requires at least 2 AZs for high availability.

```hcl
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet("10.0.0.0/16", 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
}
```

- Subnet 1: `10.0.0.0/24` in `us-east-1a`
- Subnet 2: `10.0.1.0/24` in `us-east-1b`
- `map_public_ip_on_launch = true` — nodes get a public IP automatically
- Tagged with `kubernetes.io/role/elb = 1` so Kubernetes knows these are public subnets

**Why only public subnets?**
For simplicity and cost — private subnets require a NAT Gateway (~$32/month). Since this is a short-lived demo, public subnets are sufficient.

---

### How Internet Access was set up

An Internet Gateway (IGW) connects the VPC to the internet:

```hcl
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}
```

A route table sends all outbound traffic (`0.0.0.0/0`) through the IGW:

```hcl
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}
```

Both subnets are associated with this route table so they can reach the internet.

---

### How the EKS Cluster was created

EKS needs an IAM role to manage AWS resources on your behalf:

```hcl
resource "aws_iam_role" "eks_cluster" {
  name = "timer-cluster-cluster-role"
  assume_role_policy = jsonencode({
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
```

The cluster itself:

```hcl
resource "aws_eks_cluster" "this" {
  name     = "timer-cluster"
  version  = "1.32"
  role_arn = aws_iam_role.eks_cluster.arn
  vpc_config {
    subnet_ids             = aws_subnet.public[*].id
    endpoint_public_access = true
  }
}
```

- `endpoint_public_access = true` — allows `kubectl` to connect from your laptop
- Placed in both public subnets for multi-AZ availability

---

### How the Node Group was created

Nodes are EC2 instances that run your pods. They also need an IAM role:

```hcl
resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "timer-cluster-nodes"
  instance_types  = ["t3.micro"]
  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 3
  }
}
```

- 2 nodes by default, can scale between 1-3
- Nodes run in the public subnets and get public IPs
- IAM policies attached: `AmazonEKSWorkerNodePolicy`, `AmazonEKS_CNI_Policy`, `AmazonEC2ContainerRegistryReadOnly`

---

**Resources created:**
- VPC `10.0.0.0/16` with 2 public subnets across 2 AZs
- Internet Gateway + route tables
- IAM roles for EKS cluster and nodes
- EKS cluster `timer-cluster` (Kubernetes 1.32)
- Node group: 2x `t3.micro` nodes

---

## Step 3 — Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name timer-cluster
kubectl get nodes  # verify nodes are Ready
```

---

## Step 4 — Build & Push Docker Image

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  031871828395.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repo (first time only)
aws ecr create-repository --repository-name timer-app --region us-east-1

# Build for linux/amd64 (important on Mac M-chip) and push
cd app
docker buildx build --platform linux/amd64 \
  -t 031871828395.dkr.ecr.us-east-1.amazonaws.com/timer-app:latest \
  --push .
```

> ⚠️ Always build with `--platform linux/amd64` — EKS nodes run amd64, Mac M-chips build arm64 by default.

---

## Step 5 — Deploy to Kubernetes

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl get pods  # wait for Running status
```

---

## Step 6 — Open Firewall Port

Find the node security group and allow port 30080:

```bash
# Get security group ID
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:aws:eks:cluster-name,Values=timer-cluster" \
  --query "SecurityGroups[*].[GroupId,GroupName]" --output table

# Allow port 30080
aws ec2 authorize-security-group-ingress \
  --region us-east-1 \
  --group-id <sg-id> \
  --protocol tcp --port 30080 --cidr 0.0.0.0/0
```

### Why port 30080?

Kubernetes `NodePort` services must use a port in the range **30000–32767** — this is a hard Kubernetes rule. Ports below 30000 are reserved for system use.

We chose **30080** because:
- It's in the valid NodePort range (30000–32767)
- It mirrors port `80` (standard HTTP) making it easy to remember
- It's not commonly used by other services so no conflicts

The full port flow is:
```
User browser → port 30080 (NodePort on EC2 node)
             → port 8000 (FastAPI app inside the pod)
```

The app itself runs on port `8000` internally (defined in the Dockerfile), and Kubernetes maps the external NodePort `30080` to it.

---

## Step 7 — Get Node IPs

```bash
kubectl get nodes -o wide
```

Access the app at: `http://<EXTERNAL-IP>:30080`

---

## Updating the App

After code changes:

```bash
# Rebuild and push
cd app
docker buildx build --platform linux/amd64 \
  -t 031871828395.dkr.ecr.us-east-1.amazonaws.com/timer-app:latest \
  --push .

# Restart deployment to pull new image
kubectl rollout restart deployment/timer-app
kubectl get pods  # watch new pod come up
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Pod in `ImagePullBackOff` | Check platform — rebuild with `--platform linux/amd64` |
| Terraform state lock | `terraform force-unlock -force <lock-id>` |
| EKS version not supported | Use latest supported version (currently 1.32) |
| Can't reach app in browser | Check security group has port 30080 open |
| kubectl not connecting | Re-run `aws eks update-kubeconfig` |

---

## Destroy Everything

Run in this order to avoid dependency errors:

```bash
# 1. Delete Kubernetes resources
kubectl delete -f k8s/

# 2. Destroy EKS + VPC
cd terraform/live
terraform destroy -auto-approve

# 3. Destroy state backend
cd ../bootstrap
terraform destroy -auto-approve

# 4. Delete ECR repo
aws ecr delete-repository --repository-name timer-app \
  --region us-east-1 --force
```

---

## Cost Estimate (per day)

| Resource | Cost |
|----------|------|
| EKS control plane | ~$2.40/day |
| 2x t3.micro nodes | ~$0.46/day |
| **Total** | **~$2.86/day** |

> Destroy when not in use to avoid charges.
