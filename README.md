# Digital Twin RAG - Multi-Tenant Knowledge Base System

A production-ready, multi-tenant RAG (Retrieval-Augmented Generation) system with persona-based access control, powered by OpenWebUI, Keycloak, N8N, Qdrant, and Ollama.

## Features

✅ **Multi-Tenant Isolation** - Complete data separation between tenants  
✅ **Persona-Based Access Control** - CEO, Manager, Analyst roles with distinct document access  
✅ **Enterprise Authentication** - Keycloak SSO with OAuth2/OIDC  
✅ **Scalable Storage** - S3-compatible storage (LocalStack for dev, AWS S3 for production)  
✅ **Vector Search** - Qdrant for semantic document retrieval  
✅ **Workflow Automation** - N8N for document processing pipeline  
✅ **Local LLMs** - Ollama with llama3.2 for privacy-first AI  
✅ **Docker-based** - Easy deployment with docker-compose  

## Architecture

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       ├─> [OpenWebUI] ─> [Keycloak Auth]
       │        │
       │        ├─> [Ollama LLMs]
       │        └─> [Pipeline (tenant/persona extraction)]
       │                  │
       │                  ├─> [File Upload] ─> [S3 Bucket]
       │                  │                      │
       │                  │                      └─> [N8N Workflow]
       │                  │                             │
       │                  │                             ├─> [Embedding]
       │                  │                             └─> [Qdrant Index]
       │                  │
       │                  └─> [RAG Query] ─> [Qdrant Search]
       │                                        └─> [LLM Response]
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 16GB RAM minimum
- 50GB disk space

### 1. Clone the repository

```bash
git clone https://bitbucket.org/your-org/digital-twin-rag.git
cd digital-twin-rag
```

### 2. Configure environment

```bash
cd deployment/docker
cp .env.example .env
# Edit .env with your settings
```

### 3. Start services

```bash
docker compose up -d
```

### 4. Access the system

- **OpenWebUI:** http://localhost:3000
- **Keycloak Admin:** http://localhost:8080/admin (admin/admin)
- **N8N Workflows:** http://localhost:5678
- **Qdrant Console:** http://localhost:6333/dashboard

### 5. Create users in Keycloak

1. Go to Keycloak admin console
2. Realm: `self2ai`
3. Users → Add User
4. Set email pattern: `username.tenantname@domain.com`
5. Set password

## Tenant & Persona Configuration

### Email pattern for tenant extraction:
```
alice.tenanta@gmail.com  → Tenant: tenant-tenanta
bob.tenantb@gmail.com    → Tenant: tenant-tenantb
```

### Persona mapping:
Edit `PERSONA_MAP` in:
- `workflows/openwebui/pipeline-dynamic.py`
- `services/file-sync/sync_service.py`

```python
PERSONA_MAP = {
    "alice.tenanta@gmail.com": "CEO",
    "bob.tenanta@gmail.com": "manager",
}
```

## Usage

### Upload Documents
1. Login to OpenWebUI
2. Upload files via chat interface
3. Files are stored in S3: `tenant-{tenant}/{persona}/filename.txt`
4. Automatically indexed in Qdrant

### Query Documents
1. Ask questions in chat
2. RAG retrieves relevant context from your tenant/persona documents
3. LLM generates response based on your private data

## Data Isolation

### Tenant Level:
- S3 path: `tenant-tenanta/` vs `tenant-tenantb/`
- Qdrant filter: `{tenantId: "tenant-tenanta"}`

### Persona Level:
- S3 path: `tenant-tenanta/CEO/` vs `tenant-tenanta/manager/`
- Qdrant filter: `{tenantId: "tenant-tenanta", personaId: "CEO"}`

## Scripts

### Cleanup all data:
```bash
./scripts/cleanup-all-data.sh
```

### Approve pending users:
```bash
./scripts/approve-pending-users.sh
```

### Setup ngrok tunnel (for demos):
```bash
./scripts/setup-ngrok-tunnel.sh
```

## Configuration

### Key Environment Variables:

**OpenWebUI:**
- `WEBUI_AUTH: "true"` - Enable authentication
- `ENABLE_OAUTH_SIGNUP: "true"` - Allow Keycloak signup
- `DEFAULT_USER_ROLE: "user"` - Auto-activate new users

**Keycloak:**
- Realm: `self2ai`
- Client: `openwebui`
- Client Secret: Check `.env` file

**S3/LocalStack:**
- Bucket: `digital-twin-docs`
- Endpoint: `http://localstack:4566`

**Qdrant:**
- Collection: `digital_twin_knowledge`
- Vector size: 768 (nomic-embed-text)

## Production Deployment

See `docs/aws_deployment_guide.md` for AWS deployment instructions.

## Testing

### Test tenant isolation:
1. Create 2 users in different tenants
2. Upload different documents
3. Verify each user only sees their own data

### Test persona isolation:
1. Create 2 users in same tenant, different personas
2. Upload CEO-level and manager-level documents
3. Verify persona-based access control

## Troubleshooting

### Users stuck in "pending" status:
```bash
./scripts/approve-pending-users.sh
```

### Pipeline not extracting persona:
Check PERSONA_MAP in pipeline files and update via OpenWebUI UI

### S3 upload failing:
Check LocalStack is running and bucket exists

### Qdrant not returning results:
Verify tenant/persona filters match document metadata

## Documentation

- [Architecture Overview](docs/aws_architecture.md)
- [AWS Deployment Guide](docs/aws_deployment_guide.md)
- [Persona Implementation](docs/persona_implementation.md)
- [Testing Guide](docs/isolation-testing-guide.md)

## Tech Stack

- **Frontend:** OpenWebUI
- **Auth:** Keycloak (OAuth2/OIDC)
- **LLM:** Ollama (llama3.2, nomic-embed-text)
- **Vector DB:** Qdrant
- **Storage:** S3-compatible (LocalStack/AWS S3)
- **Workflow:** N8N
- **Database:** PostgreSQL (Keycloak), SQLite (OpenWebUI)

## License

MIT

## Support

For issues and questions, contact: your-team@domain.com
