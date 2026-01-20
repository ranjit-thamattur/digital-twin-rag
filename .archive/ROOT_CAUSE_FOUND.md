# FOUND THE ISSUE!

## ❌ Two Problems:

### 1. Workflow Not Registered in N8N
```
Error: The requested webhook "POST upload-document" is not registered.
```

**This means the workflow is NOT imported or NOT activated!**

### 2. Ollama is Unhealthy
```
ollama Up 5 hours (unhealthy)
```

**Ollama works but might be slow/unreliable**

---

## ✅ FIXES:

### Fix 1: Import & Activate Workflow

**Steps:**
1. Open N8N: http://localhost:5678
2. Check if "Digital Twin - Upload (Multi-tenant)" exists
3. If NO → Import from file:
   - File: `/workflows/n8n/Digital Twin - Upload (Multi-tenant).json`
4. If YES → Open it
5. **Toggle ACTIVATE (must be ON!)** ← CRITICAL!
6. Save

**The webhook only registers when workflow is ACTIVE!**

---

### Fix 2: Restart Ollama

```bash
docker restart ollama

# Wait 30 seconds
sleep 30

# Test
curl -X POST http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "test"}' | jq '.embedding | length'

# Should return: 384
```

---

## ✅ After Both Fixes:

1. **Webhook will be registered** ✅
2. **Ollama will be healthy** ✅
3. **Upload will work** ✅

---

## Test Upload:

```bash
curl -X POST http://localhost:5678/webhook/upload-document \
  -H 'Content-Type: application/json' \
  -d '{
    "fileName": "test.txt",
    "content": "This is a test document for indexing",
    "metadata": {
      "tenantId": "tenant-fridayfilmhouse",
      "personaId": "test"
    }
  }'
```

**Should return:**
```json
{
  "success": true,
  "message": "Indexed X chunks",
 ...
}
```

---

## Verify in Qdrant:

```bash
curl http://localhost:6333/collections/tenant-fridayfilmhouse_knowledge | \
  jq '.result.points_count'

# Should show number of chunks!
```

---

**The workflow was never activated - that's why webhook wasn't registered!** ✅

Activate it in N8N and it will work! 🚀
