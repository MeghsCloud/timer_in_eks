# Timer App on EKS

A real-time shared timer app built with Python FastAPI + WebSockets, deployed on AWS EKS using Terraform.

## Architecture

```
Internet → NodePort (30080) → EKS Pod → FastAPI WebSocket App
```

## Prerequisites

- AWS CLI configured (`aws configure`)
- terraform, kubectl, docker installed
- AWS account ID: `031871828395`

## Deploy from Scratch

### 1. Bootstrap remote state
```bash
cd terraform/bootstrap
terraform init
terraform apply -auto-approve
```

### 2. Create EKS cluster
```bash
cd terraform/live
terraform init
terraform apply -auto-approve
```

### 3. Configure kubectl
```bash
aws eks update-kubeconfig --region us-east-1 --name timer-cluster
```

### 4. Build and push Docker image
```bash
aws ecr create-repository --repository-name timer-app --region us-east-1

aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin 031871828395.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 \
  -t 031871828395.dkr.ecr.us-east-1.amazonaws.com/timer-app:latest \
  --push app/
```

### 5. Deploy to Kubernetes
```bash
kubectl apply -f k8s/
```

### 6. Open port 30080
```bash
# Get the node security group ID
SG_ID=$(aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:aws:eks:cluster-name,Values=timer-cluster" \
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --region us-east-1 \
  --group-id $SG_ID --protocol tcp --port 30080 --cidr 0.0.0.0/0
```

### 7. Get the app URL
```bash
kubectl get nodes -o wide
# Use EXTERNAL-IP:30080
```

## Destroy Everything
```bash
kubectl delete -f k8s/
cd terraform/live && terraform destroy -auto-approve
cd ../bootstrap && terraform destroy -auto-approve
aws ecr delete-repository --repository-name timer-app --region us-east-1 --force
```

## App Access
- URL: `http://<node-external-ip>:30080`
- Supports unlimited concurrent users
- All users see the same synced timer in real time
