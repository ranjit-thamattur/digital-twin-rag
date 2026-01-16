# Multi-Tenant RAG - AWS Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Cloud (us-east-1)                        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Public Subnet (DMZ)                         │ │
│  │                                                                │ │
│  │  ┌──────────────┐         ┌──────────────┐                   │ │
│  │  │  CloudFront  │────────▶│     ALB      │                   │ │
│  │  │     CDN      │         │ (Port 443)   │                   │ │
│  │  └──────────────┘         └───────┬──────┘                   │ │
│  │                                    │                           │ │
│  └────────────────────────────────────┼───────────────────────────┘ │
│                                       │                              │
│  ┌────────────────────────────────────┼───────────────────────────┐ │
│  │                  Private Subnet (Application Tier)            │ │
│  │                                    │                           │ │
│  │  ┌─────────────────────────────────▼──────────────────────┐   │ │
│  │  │              ECS/Fargate Cluster                        │   │ │
│  │  │                                                         │   │ │
│  │  │  ┌────────────────┐  ┌────────────────┐  ┌──────────┐ │   │ │
│  │  │  │   OpenWebUI    │  │      N8N       │  │  Qdrant  │ │   │ │
│  │  │  │   Container    │  │   Workflow     │  │  Vector  │ │   │ │
│  │  │  │   (Port 8080)  │──│   Container    │──│    DB    │ │   │ │
│  │  │  │                │  │   (Port 5678)  │  │ (Port    │ │   │ │
│  │  │  │ ┌────────────┐ │  │                │  │  6333)   │ │   │ │
│  │  │  │ │ File-Sync  │ │  │                │  │          │ │   │ │
│  │  │  │ │  Service   │ │  │                │  │          │ │   │ │
│  │  │  │ └────────────┘ │  │                │  │          │ │   │ │
│  │  │  └────────┬───────┘  └───────┬────────┘  └──────────┘ │   │ │
│  │  │           │                  │                         │   │ │
│  │  └───────────┼──────────────────┼─────────────────────────┘   │ │
│  │              │                  │                             │ │
│  └──────────────┼──────────────────┼─────────────────────────────┘ │
│                 │                  │                                │
│  ┌──────────────▼──────────┐  ┌───▼──────────────────────────────┐ │
│  │       Amazon S3         │  │    AWS Bedrock (Managed)        │ │
│  │  digital-twin-docs      │  │                                 │ │
│  │                         │  │  ┌────────────────────────────┐ │ │
│  │  tenant-tenanta/        │  │  │  Claude 3 Sonnet          │ │ │
│  │    user/files           │  │  │  - Response: 2-4s ✅      │ │ │
│  │  tenant-tenantb/        │  │  │  - Auto-scaling           │ │ │
│  │    user/files           │  │  │  - Managed service        │ │ │
│  │                         │  │  └────────────────────────────┘ │ │
│  └─────────────────────────┘  └─────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                 Data Tier (Private Subnet)                   │  │
│  │                                                              │  │
│  │  ┌──────────────────────┐      ┌──────────────────────┐    │  │
│  │  │   RDS PostgreSQL     │      │  ElastiCache Redis   │    │  │
│  │  │   - Keycloak DB      │      │  - Session Cache     │    │  │
│  │  │   - OpenWebUI DB     │      │  - Query Cache       │    │  │
│  │  │   - Multi-AZ HA      │      │  - Optional          │    │  │
│  │  └──────────────────────┘      └──────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Descriptions

### Frontend Layer

#### CloudFront CDN
- **Purpose**: Content delivery and SSL termination
- **Benefits**: 
  - Global edge locations
  - DDoS protection via AWS Shield
  - SSL/TLS certificates via ACM
  - Static asset caching

#### Application Load Balancer (ALB)
- **Purpose**: Traffic distribution and health checks
- **Features**:
  - Path-based routing
  - SSL termination
  - WebSocket support for N8N
  - Health check endpoints

### Application Layer (ECS Cluster)

#### OpenWebUI Container
- **Image**: `ghcr.io/open-webui/open-webui:main`
- **Resources**: 1 vCPU, 2GB RAM
- **Ports**: 8080 (internal)
- **Environment**:
  - Keycloak SSO integration
  - PostgreSQL connection
  - Pipeline mounting

#### N8N Workflow Container
- **Image**: `n8nio/n8n:latest`
- **Resources**: 2 vCPU, 4GB RAM
- **Ports**: 5678 (internal)
- **Storage**: EFS for workflow persistence
- **Workflows**:
  - Digital Twin Upload (Multi-tenant)
  - Digital Twin Chat RAG (Multi-tenant)

#### Qdrant Vector DB Container
- **Image**: `qdrant/qdrant:latest`
- **Resources**: 2 vCPU, 8GB RAM
- **Storage**: EBS volume (100GB, gp3)
- **Collections**: 
  - `digital_twin_knowledge` (768-dim vectors)

#### File-Sync Service Container
- **Image**: Custom Python application
- **Resources**: 0.5 vCPU, 1GB RAM
- **Purpose**: Monitor OpenWebUI uploads → S3 sync

### Storage Layer

#### Amazon S3
- **Bucket**: `digital-twin-docs-prod`
- **Structure**:
  ```
  /tenant-{tenantId}/
    /{personaId}/
      /documents/
  ```
- **Features**:
  - Versioning enabled
  - Server-side encryption (SSE-S3)
  - Lifecycle policies (archive to Glacier after 90 days)
  - Cross-region replication (optional)

### AI/ML Layer

#### AWS Bedrock
- **Model**: Claude 3 Sonnet (Anthropic)
- **Alternative Models**:
  - Titan Text (AWS native)
  - LLaMA 2 70B (Meta)
  - Mistral Large
- **Performance**: 2-4 second responses
- **Pricing**: Pay-per-token (~$0.003 per query)
- **Features**:
  - Automatic scaling
  - No infrastructure management
  - Latest model versions
  - Built-in guardrails

### Data Layer

#### RDS PostgreSQL
- **Instance**: db.t3.medium (Multi-AZ)
- **Databases**:
  - `keycloak` - User authentication and realm data
  - `openwebui` - User profiles, chats, file metadata
  - `n8n` - Workflow execution history
- **Backup**: Automated daily snapshots (7-day retention)
- **Security**: Encryption at rest, VPC isolation

#### ElastiCache Redis (Optional)
- **Purpose**: Response and session caching
- **Benefits**: 
  - Cache repeated queries (instant response)
  - Session management
  - Rate limiting

## Data Flow Diagrams

### File Upload Flow

```
User Browser
    │
    │ 1. Upload file
    ▼
CloudFront → ALB → OpenWebUI
                      │
                      │ 2. Save to DB + local storage
                      ▼
                 File-Sync Service
                      │
                      ├─ 3a. Upload to S3
                      │      │
                      │      ▼
                      │   S3 Bucket
                      │   (tenant-{id}/user/file.txt)
                      │
                      └─ 3b. Trigger N8N
                             │
                             ▼
                          N8N Workflow
                             │
                             ├─ 4a. Generate embeddings
                             │      (Bedrock Titan)
                             │
                             └─ 4b. Store in Qdrant
                                    │
                                    ▼
                                 Qdrant
                                 (vector + metadata)
```

### Chat Query Flow

```
User Question
    │
    ▼
CloudFront → ALB → OpenWebUI
                      │
                      │ 1. Query with __user__
                      ▼
                   Pipeline
                      │
                      │ 2. Extract tenant from __user__.email
                      │    (diana.tenantb@gmail.com → tenant-tenantb)
                      ▼
                   N8N Chat RAG
                      │
                      ├─ 3. Search Qdrant
                      │   (filter: tenantId = tenant-tenantb)
                      │      │
                      │      ▼
                      │   Qdrant
                      │   Returns: Top 3 relevant chunks
                      │
                      └─ 4. Generate answer
                          (Bedrock: context + question)
                             │
                             ▼
                          Bedrock Claude
                          Response: "$5,000,000" (2-4s)
                             │
                             ▼
                          Pipeline → OpenWebUI → User
```

## Network Architecture

### VPC Configuration

```
VPC: 10.0.0.0/16

┌─ Public Subnets (10.0.1.0/24, 10.0.2.0/24)
│  - ALB
│  - NAT Gateway
│
├─ Private Subnets - App Tier (10.0.10.0/24, 10.0.11.0/24)
│  - ECS Tasks (OpenWebUI, N8N, Qdrant)
│  - File-Sync Service
│
└─ Private Subnets - Data Tier (10.0.20.0/24, 10.0.21.0/24)
   - RDS PostgreSQL
   - ElastiCache Redis
```

### Security Groups

```
ALB Security Group:
  Inbound: 443 from 0.0.0.0/0 (HTTPS)
  Outbound: 8080 to ECS-SG

ECS Security Group:
  Inbound: 8080 from ALB-SG (OpenWebUI)
           5678 from ECS-SG (N8N internal)
           6333 from ECS-SG (Qdrant)
  Outbound: All to VPC (internal services)
            443 to 0.0.0.0/0 (Bedrock API)

RDS Security Group:
  Inbound: 5432 from ECS-SG
  Outbound: None
```

## Scalability Design

### Auto-Scaling Configuration

#### ECS Service Auto-Scaling
```yaml
OpenWebUI:
  Min: 2
  Desired: 2
  Max: 10
  Scaling Metric: CPU > 70%
  
N8N:
  Min: 2
  Desired: 3
  Max: 20
  Scaling Metric: Custom (queue depth)

Qdrant:
  Min: 2
  Desired: 2
  Max: 5
  Scaling Metric: Memory > 80%
```

#### Bedrock
- **Built-in auto-scaling** (no configuration needed)
- Handles traffic spikes automatically
- Pay only for actual usage

## High Availability

### Multi-AZ Deployment

```
Availability Zone A          Availability Zone B
────────────────────────────────────────────────
ALB (Active)         ←→      ALB (Active)
ECS Tasks (2)        ←→      ECS Tasks (2)
RDS Primary          ←→      RDS Standby
ElastiCache Node     ←→      ElastiCache Replica
```

### Failover Strategy
- **ALB**: Cross-zone load balancing
- **RDS**: Automatic failover (60s)
- **ECS**: Tasks distributed across AZs
- **S3**: 99.999999999% durability (built-in)

## Monitoring & Observability

### CloudWatch Dashboards

```
Dashboard: RAG-System-Health
├─ Response Times (p50, p95, p99)
├─ Error Rates (4xx, 5xx)  
├─ Tenant Query Distribution
├─ Bedrock API Latency
├─ Qdrant Search Performance
└─ ECS Resource Utilization
```

### Alarms

```
Critical Alarms:
- Response time > 10s (sustained)
- Error rate > 5%
- RDS CPU > 90%
- ECS memory > 95%

Warning Alarms:
- Response time > 6s
- Bedrock throttling detected
- S3 4xx errors
```

## Cost Optimization

### Reserved Capacity

```
Service              RI/Savings Plan   Monthly Savings
───────────────────────────────────────────────────────
RDS (db.t3.medium)   1-year RI        30%
ECS Fargate          Compute SP       20%
───────────────────────────────────────────────────────
Total Savings:                        ~$100/month
```

### Right-Sizing Recommendations

- Start with t3/t4g instances
- Monitor for 2 weeks
- Right-size based on actual usage
- Use Compute Optimizer recommendations

## Deployment Pipeline

```
GitHub
  │
  │ git push
  ▼
GitHub Actions
  │
  ├─ Build containers
  ├─ Run tests
  ├─ Push to ECR
  │
  ▼
AWS CodePipeline
  │
  ├─ Dev → Staging → Prod
  ├─ Blue/Green deployment
  │
  ▼
ECS Service Update
  │
  └─ Gradual rollout (10% → 50% → 100%)
```

## Disaster Recovery

### Backup Strategy

```
Component        Backup Frequency    Retention
─────────────────────────────────────────────
RDS              Daily + PITR        7 days
S3               Versioning          30 days
Qdrant Snapshots Weekly              4 weeks
ECS Config       Git versioned       Indefinite
```

### Recovery Procedures

**RTO (Recovery Time Objective):** 1 hour  
**RPO (Recovery Point Objective):** 15 minutes

```
Disaster Scenario        Recovery Steps
───────────────────────────────────────────
Region failure          → Failover to DR region (automated)
Data corruption         → Restore from latest backup
Service outage          → Auto-scaling + health checks
```

## Security Architecture

### IAM Roles

```
ECS Task Role (OpenWebUI):
  - S3: GetObject, ListBucket
  - RDS: Connect
  - CloudWatch: PutMetricData

ECS Task Role (N8N):
  - S3: GetObject, PutObject
  - Bedrock: InvokeModel
  - Qdrant: All operations

ECS Task Role (File-Sync):
  - S3: PutObject, GetObject
  - RDS: Connect (read-only)
```

### Encryption

- **In Transit**: TLS 1.3 (ALB, Bedrock)
- **At Rest**: 
  - S3: SSE-S3
  - RDS: AES-256
  - EBS: Encrypted volumes

## Summary

**Architecture Type:** Microservices on AWS ECS with Managed AI

**Key Benefits:**
- ✅ 3-4x faster than local (3-5s vs 12-14s)
- ✅ Auto-scaling for variable load
- ✅ High availability (Multi-AZ)
- ✅ Managed AI (Bedrock - no model ops)
- ✅ Cost-effective ($200-500/month for production)

**Production Readiness:**
- Security: ✅ VPC isolation, encryption, IAM
- Reliability: ✅ Multi-AZ, auto-scaling, health checks
- Performance: ✅ Sub-5s response times
- Monitoring: ✅ CloudWatch dashboards & alarms
