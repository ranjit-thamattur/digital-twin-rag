# Quick Start Guide

Get your Digital Twin RAG system running in **5 minutes**.

---

## Prerequisites

- Docker & Docker Compose installed
- 8GB RAM minimum
- AWS CLI (optional, for LocalStack)

---

## Step 1: Start Services (2 minutes)

```bash
cd deployment/docker
docker-compose up -d

# Wait for services to start
docker-compose ps
```

Expected output:
```
NAME        STATUS
n8n-dt      Up (healthy)
ollama      Up (healthy)
qdrant      Up
openwebui   Up
localstack  Up (healthy)  # Optional
```

---

## Step 2: Pull AI Models (2 minutes)

```bash
# Embedding model (required)
docker exec -it ollama ollama pull nomic-embed-text

# Chat model (required)
docker exec -it ollama ollama pull llama3.2

# Verify
docker exec ollama ollama list
```

---

## Step 3: Setup Qdrant & LocalStack (1 minute)

```bash
cd ../../scripts/setup
./setup-complete.sh
```

This creates:
- ✅ Qdrant collection + indexes
- ✅ S3 bucket (LocalStack)
- ✅ Lambda function
- ✅ EventBridge rules

---

## Step 4: Import Workflows (30 seconds)

### **n8n Workflows:**

1. Open: http://localhost:5678
2. Click **Workflows** → **Import from File**
3. Import both files from `workflows/n8n/`:
   - `chat-multitenant.json`
   - `upload-multitenant.json`
4. **Activate** both workflows (toggle in top-right)

### **Open WebUI Pipeline:**

1. Open: http://localhost:3000
2. **Admin Panel** → **Settings** → **Pipelines**
3. Click **Import**
4. Upload `workflows/openwebui/pipeline-dynamic.py`
5. Configure in **Valves**:
   - `TENANT_MODE`: `email_domain`
   - Save

---

## Step 5: Test (30 seconds)

### **Upload a document:**

```bash
cd ../../examples/data

# Upload test file
curl -X POST http://localhost:5678/webhook/upload-document \
  -H "Content-Type: application/json" \
  -d '{
    "fileName": "test.txt",
    "content": "ACME Corp Q4 Revenue: $2.5M",
    "metadata": {
      "tenantId": "tenant-acme",
      "personaId": "CEO"
    }
  }'
```

### **Query:**

```bash
# Direct query to n8n
curl -X POST http://localhost:5678/webhook/openwebui \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What was the revenue?",
    "tenantId": "tenant-acme",
    "personaId": "CEO"
  }' | jq -r '.response'
```

### **Or use Open WebUI:**

1. Go to http://localhost:3000
2. Start chat
3. Ask: "What information do we have?"
4. Should return info from uploaded document ✅

---

## Verify Everything Works

```bash
# Check Qdrant has data
curl http://localhost:6333/collections/digital_twin_knowledge | jq '.result.points_count'

# Should show: > 0

# Check workflows active
curl http://localhost:5678/webhooks | jq

# Should show: webhook endpoints
```

---

## Next Steps

- Read [Architecture](ARCHITECTURE.md) to understand data flow
- See [Deployment](DEPLOYMENT.md) for production setup
- Check [API](API.md) for endpoint documentation
- Review [Troubleshooting](TROUBLESHOOTING.md) for common issues

---

## Common Issues

### **Services won't start**
```bash
docker-compose down
docker-compose up -d
docker-compose logs -f
```

### **Models not found**
```bash
docker exec -it ollama ollama pull nomic-embed-text
docker exec -it ollama ollama pull llama3.2
```

### **Workflows return 404**
- Check they're **Active** in n8n
- Verify webhook URLs match configuration

### **No search results**
- Wait 10-20 seconds after upload
- Check Qdrant: `curl http://localhost:6333/collections/digital_twin_knowledge`
- Verify indexes: `../../scripts/setup/create_qdrant_indexes.sh`

---

## You're Ready!

Your multi-tenant RAG system is now running. Upload documents and start querying! 🎉

**Need help?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md)
