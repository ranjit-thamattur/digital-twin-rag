# CloneMind AI: QA Architecture & Pricing

This document outlines the cost-optimized architecture for the CloneMind Digital Twin RAG system in a QA/Development environment.

## 🏗️ Technical Architecture

The platform has been migrated from a manual n8n workflow system to a programmatic **Model Context Protocol (MCP)** orchestration layer.

### 1. The Core Components
*   **Identity Layer**: AWS Cognito handles user authentication. The **Tenant Service** maps these identities to specific "DNA" (Tone, Industry, Persona).
*   **Orchestration Layer**: The **MCP Server** (Python) replaces n8n. It handles model routing, RAG search logic, and document ingestion triggers.
*   **Knowledge Layer**: **Qdrant** stores vector embeddings with strict tenant isolation.
*   **Persistence Layer**: **AWS EFS** provides shared persistence for containers, ensuring data survives restarts.

### 2. Service Sizing (QA Profile)

All services are containerized and run on **ECS with EC2 (t3.micro/small)** capacity.

| Service | Infrastructure | CPU (vCPU) | RAM (MB) | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **OpenWebUI** | ECS Container | 0.5 | 512 | Main Chat & Admin UI |
| **FileSync** | Sidecar | 0.1 | 128 | Background S3 sync from DB |
| **MCP Server** | ECS Container | 0.2 | 256 | AI Twin routing & tools |
| **Tenant Service** | ECS Container | 0.2 | 256 | User-to-Tenant lookup |
| **Qdrant** | ECS Container | 0.2 | 256 | Vector Knowledge Base |
| **Redis** | ECS Container | 0.1 | 256 | Session & Cache management |
| **S3 Processor** | Lambda | - | 512 | Text parsing & extraction |

---

## 💰 Estimated Monthly Pricing (QA Env)

*Based on AWS us-east-1 pricing as of Jan 2026.*

### 1. Free Tier vs. Paid (Comparison)

By removing the Application Load Balancer (ALB), we have reduced the base cost for old accounts by over 60%.

| AWS Resource | New Account (<12m) | Old Account | Free Tier Details |
| :--- | :--- | :--- | :--- |
| **ECS / EC2** | $0.00 | $7.50 | 750 hrs/mo of `t3.micro`. |
| **ALB (Load Balancer)** | $0.00 | **$0.00** | **REMOVED** for cost savings. |
| **S3 / Lambda** | $0.00 | $0.50 | 5GB S3, 1M Lambda requests. |
| **EFS (Storage)** | $0.00 | $3.00 | 5GB Storage (First 12m). |
| **Cognito** | $0.00 | $0.00 | Always Free for <50k MAU. |
| **Bedrock (LLM)** | ~$3.00 | ~$3.00 | Pay-as-you-go (No free tier). |
| **TOTAL** | **~$3.00** | **~$14.00** | *Zero-ALB setup saves $22/mo.* |

### 2. Service-Specific Cost Optimization

*   **Compute (EC2)**: We use **t3.micro** instances instead of Fargate. Fargate costs ~$40+; EC2 saves >70%.
*   **Zero-ALB Architecture**: We have eliminated the ALB ($22/mo). Services are accessed directly via the EC2 Public IP on specific ports.
*   **Lambda (S3 Processor)**: Remains **$0.00** forever due to the "Always Free" 1 Million requests tier.
*   **Bedrock (LLMs)**: **Intelligent Routing** in the MCP Server sends simple queries to Claude 3.5 Haiku, keeping usage costs minimal.

---

## 🚀 Key Deployment Details (No ALB Mode)

1.  **Direct Port Access**: The system exposes services directly via the EC2 Public IP.
    *   `http://[EC2-IP]:8080` → **OpenWebUI** (Chat)
    *   `http://[EC2-IP]:8000` → **Tenant Management** (API)
    *   `http://[EC2-IP]:6333` → **Qdrant Dashboard** (Internal)
2.  **Internal Discovery**: Services continue to communicate securely via AWS Cloud Map (`.clonemind.local`) within the VPC.
3.  **Authentication Callback**: The Cognito User Pool remains configured with `http://localhost:3000/oauth/callback` for seamless local-to-cloud development.

## 🛠️ Maintenance Commands

*   **Find Public IP**: `aws ec2 describe-instances --filters "Name=tag:Name,Values=CloneMindCluster/DefaultCapacity" --query "Reservations[*].Instances[*].PublicIpAddress" --output text`
*   **View Infrastructure Logs**: `aws logs tail /aws/ecs/clonemind-openwebui`
*   **Redeploy Stack**: `cdk deploy`
*   **Check Vector Health**: `curl http://[EC2-IP]:6333/health`
