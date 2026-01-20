# Digital Twin RAG - Folder Structure

## 📁 Complete Project Structure

```
digital-twin-rag/
│
├── 📄 README.md                         # Main documentation
├── 📄 LICENSE                           # MIT License
├── 📄 CHANGELOG.md                      # Version history
│
├── 📂 docs/                             # Documentation
│   ├── QUICKSTART.md                   # 5-minute setup guide
│   ├── ARCHITECTURE.md                 # System design
│   ├── DEPLOYMENT.md                   # Production deployment
│   ├── API.md                          # API reference
│   ├── TROUBLESHOOTING.md              # Common issues
│   └── CONTRIBUTING.md                 # Contribution guide
│
├── 📂 workflows/                        # Workflow definitions
│   ├── 📂 n8n/                         # n8n workflows
│   │   ├── chat-original.json          # Basic chat workflow
│   │   ├── chat-multitenant.json       # Multi-tenant chat
│   │   ├── upload-original.json        # Basic upload workflow
│   │   └── upload-multitenant.json     # Multi-tenant upload
│   │
│   └── 📂 openwebui/                   # Open WebUI pipelines
│       ├── pipeline-dynamic.py         # Auto tenant assignment
│       ├── pipeline-fixed.py           # Fixed tenant config
│       └── pipeline-auto.py            # Email-based tenants
│
├── 📂 deployment/                       # Deployment configs
│   ├── 📂 docker/                      # Docker setup
│   │   ├── docker-compose.yml          # Main compose file
│   │   ├── .env.example                # Environment template
│   │   └── Dockerfile.watcher          # File watcher image
│   │
│   ├── 📂 localstack/                  # LocalStack (dev)
│   │   ├── 📂 lambda/                  # Lambda functions
│   │   │   └── lambda_function.py      # S3 processor
│   │   └── setup-localstack.sh         # LocalStack setup
│   │
│   └── 📂 aws/                         # AWS (production)
│       ├── 📂 terraform/               # Infrastructure as Code
│       ├── 📂 cloudformation/          # CloudFormation templates
│       └── README.md                   # AWS deployment guide
│
├── 📂 scripts/                          # Utility scripts
│   ├── 📂 setup/                       # Setup scripts
│   │   ├── setup-complete.sh           # Complete system setup
│   │   ├── setup-qdrant.sh             # Qdrant initialization
│   │   ├── setup-ollama.sh             # Pull AI models
│   │   └── create_qdrant_indexes.sh    # Create indexes
│   │
│   ├── 📂 utils/                       # Helper utilities
│   │   ├── upload-s3.py                # S3 upload helper
│   │   ├── upload_to_s3.sh             # Bash upload script
│   │   ├── query-qdrant.sh             # Query vector DB
│   │   └── test-system.sh              # System health check
│   │
│   └── 📂 backup/                      # Backup scripts
│       ├── backup-qdrant.sh            # Backup vector DB
│       └── restore-qdrant.sh           # Restore from backup
│
├── 📂 config/                           # Configuration files
│   ├── qdrant-indexes.json             # Index definitions
│   ├── tenant-mapping.json             # Tenant mappings
│   └── models.json                     # Model configurations
│
├── 📂 examples/                         # Example files
│   ├── 📂 data/                        # Sample documents
│   │   ├── tenant-acme.txt             # ACME Corp data
│   │   └── tenant-globex.txt           # Globex Inc data
│   │
│   └── 📂 queries/                     # Example queries
│       └── test-queries.json           # Test query set
│
└── 📂 tests/                            # Test suite
    ├── test-upload.sh                  # Upload tests
    ├── test-query.sh                   # Query tests
    └── test-multitenancy.sh            # Tenant isolation tests
```

---

## 📋 File Descriptions

### **Root Level**

| File | Purpose |
|------|---------|
| `README.md` | Main project documentation with quick start |
| `LICENSE` | MIT License |
| `CHANGELOG.md` | Version history and release notes |

### **docs/**

Comprehensive documentation for users and developers.

| File | Description |
|------|-------------|
| `QUICKSTART.md` | Get running in 5 minutes |
| `ARCHITECTURE.md` | System design, data flow, components |
| `DEPLOYMENT.md` | Production deployment guide |
| `API.md` | API endpoints and usage |
| `TROUBLESHOOTING.md` | Common issues and solutions |
| `CONTRIBUTING.md` | How to contribute |

### **workflows/**

All workflow and pipeline definitions.

#### **workflows/n8n/**

| File | Purpose |
|------|---------|
| `chat-original.json` | Basic chat workflow (single-tenant) |
| `chat-multitenant.json` | Multi-tenant chat with filtering |
| `upload-original.json` | Basic upload workflow |
| `upload-multitenant.json` | Multi-tenant upload with metadata |

#### **workflows/openwebui/**

| File | Purpose |
|------|---------|
| `pipeline-dynamic.py` | Auto tenant assignment (email/ID) |
| `pipeline-fixed.py` | Manual tenant configuration |
| `pipeline-auto.py` | Email domain-based tenants |

### **deployment/**

Deployment configurations for different environments.

#### **deployment/docker/**

| File | Purpose |
|------|---------|
| `docker-compose.yml` | All services definition |
| `.env.example` | Environment variables template |
| `Dockerfile.watcher` | File watcher service |

#### **deployment/localstack/**

| File | Purpose |
|------|---------|
| `lambda/lambda_function.py` | S3 upload processor |
| `setup-localstack.sh` | LocalStack initialization |

#### **deployment/aws/**

Production AWS deployment configurations (Terraform, CloudFormation).

### **scripts/**

Automation and utility scripts.

#### **scripts/setup/**

| Script | Purpose |
|--------|---------|
| `setup-complete.sh` | One-command complete setup |
| `setup-qdrant.sh` | Initialize Qdrant only |
| `setup-ollama.sh` | Pull AI models |
| `create_qdrant_indexes.sh` | Create vector indexes |

#### **scripts/utils/**

| Script | Purpose |
|--------|---------|
| `upload-s3.py` | Upload files to S3 (Python) |
| `upload_to_s3.sh` | Upload files to S3 (Bash) |
| `query-qdrant.sh` | Query vector database |
| `test-system.sh` | Health check all services |

#### **scripts/backup/**

| Script | Purpose |
|--------|---------|
| `backup-qdrant.sh` | Backup vector database |
| `restore-qdrant.sh` | Restore from backup |

### **config/**

Configuration files for the system.

| File | Purpose |
|------|---------|
| `qdrant-indexes.json` | Vector index definitions |
| `tenant-mapping.json` | Email→Tenant mappings |
| `models.json` | AI model configurations |

### **examples/**

Sample data and queries for testing.

#### **examples/data/**

| File | Purpose |
|------|---------|
| `tenant-acme.txt` | Sample ACME Corp data |
| `tenant-globex.txt` | Sample Globex Inc data |

#### **examples/queries/**

| File | Purpose |
|------|---------|
| `test-queries.json` | Example queries for testing |

### **tests/**

Test scripts for validation.

| Script | Purpose |
|--------|---------|
| `test-upload.sh` | Test document upload |
| `test-query.sh` | Test query functionality |
| `test-multitenancy.sh` | Test tenant isolation |

---

## 🎯 Usage Patterns

### **Quick Start**
```bash
# Extract package
tar -xzf digital-twin-rag-complete.tar.gz
cd digital-twin-rag

# Follow quickstart
cat docs/QUICKSTART.md

# Run setup
cd deployment/docker && docker-compose up -d
cd ../../scripts/setup && ./setup-complete.sh
```

### **Development**
```bash
# Use LocalStack for AWS emulation
cd deployment/localstack
./setup-localstack.sh

# Test uploads
cd ../../scripts/utils
./upload-s3.py ../../examples/data/tenant-acme.txt tenant-acme CEO
```

### **Production**
```bash
# Deploy to AWS
cd deployment/aws/terraform
terraform init
terraform apply

# Configure production
cd ../../../config
# Edit tenant-mapping.json, models.json
```

---

## 📦 What's Included

- ✅ **37 files** organized in logical structure
- ✅ **Complete documentation** from setup to deployment
- ✅ **4 workflow files** (2 original + 2 multi-tenant)
- ✅ **3 pipeline variations** for different use cases
- ✅ **Setup scripts** for automated deployment
- ✅ **Example data** for immediate testing
- ✅ **Test suite** for validation
- ✅ **AWS templates** for production

---

## 🚀 Next Steps

1. **Extract the package**: `tar -xzf digital-twin-rag-complete.tar.gz`
2. **Read QUICKSTART**: `cat docs/QUICKSTART.md`
3. **Start services**: `cd deployment/docker && docker-compose up -d`
4. **Run setup**: `cd ../../scripts/setup && ./setup-complete.sh`
5. **Test**: Upload examples and query

**You're ready to build!** 🎉
