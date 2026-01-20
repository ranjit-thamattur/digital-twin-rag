# Troubleshooting: Upload Not Creating Vectors in Qdrant

## Possible Issues:

### 1. Check N8N Execution
**In N8N UI (http://localhost:5678):**
- Open the Upload workflow
- Check "Executions" tab
- Look for errors in any node
- Common failures:
  - Embedding generation fails
  - Merge node has no data
  - Insert Qdrant gets empty data

### 2. Check Which Node is Failing
**Common failure points:**
- ❌ **Generate Embedding**: Ollama not responding
- ❌ **Merge Paths**: No data passing through
- ❌ **Prepare JSON**: Wrong data format
- ❌ **Insert Qdrant**: Collection name mismatch

### 3. Debug Steps

**Step 1: Check if Ollama embeddings work**
```bash
curl -X POST http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "test"}' | jq '.embedding | length'

# Should return: 384
```

**Step 2: Check Qdrant collection exists**
```bash
curl http://localhost:6333/collections/tenant-fridayfilmhouse_knowledge | jq .result.status

# Should return: "green"
```

**Step 3: Test manual insert**
```bash
curl -X PUT http://localhost:6333/collections/tenant-fridayfilmhouse_knowledge/points \
  -H 'Content-Type: application/json' \
  -d '{
    "points": [{
      "id": "test-123",
      "vector": [0.1, 0.2, ...],  # 384 values
      "payload": {"text": "test"}
    }]
  }'
```

### 4. Check Workflow Data Flow

**In N8N, after execution:**

**a) Check "Generate Embedding" output:**
- Should have: `embedding` array (384 numbers)
- Should have: all metadata (tenantId, fileName, etc.)

**b) Check "Prepare Qdrant Point" output:**
- Should have: `id` (UUID)
- Should have: `vector` (array of 384 numbers)
- Should have: `collectionName`
- Should have: `payload` object

**c) Check "Merge Paths" output:**
- Should have data from "Prepare Qdrant Point"
- Look for: `id`, `vector`, `payload`

**d) Check "Prepare JSON" output:**
- Should be: `{"points": [...]}`
- Points array should have objects with `id`, `vector`, `payload`

**e) Check "Insert Qdrant" output:**
- Should be: `{"result": ..., "status": "ok"}`

---

## Common Fixes:

### Fix 1: Merge Node Empty
**Problem:** Merge node outputs nothing

**Solution:** Change connections
```
Instead of:
  IF → [TRUE] → Create → Merge
  IF → [FALSE] → Merge

Try:
  Prepare Point → Check → IF → Both branches → Merge
```

### Fix 2: Wrong Collection Name
**Problem:** Trying to insert to wrong collection

**Check in "Insert Qdrant" node:**
```
URL should be:
http://qdrant:6333/collections/{{$('Prepare Qdrant Point').item.json.collectionName}}/points

NOT:
http://qdrant:6333/collections/digital_twin_knowledge/points
```

### Fix 3: Data Not Passing Through Merge
**Problem:** Merge with "append" mode might duplicate or lose data

**Solution:** Use code node after merge to get original data:
```javascript
// After merge, get data from Prepare Qdrant Point
const prepareNode = $('Prepare Qdrant Point');
return prepareNode.all();
```

### Fix 4: Empty Embedding
**Problem:** Ollama not generating embeddings

**Check:**
```bash
docker logs ollama --tail 50 | grep error
```

**Fix:**
```bash
# Restart Ollama
docker restart ollama

# Wait and test
sleep 10
curl -X POST http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "test"}'
```

---

## Quick Test Workflow:

**Minimal test to isolate issue:**

1. **Manual trigger** in N8N with test data:
```json
{
  "fileName": "test.txt",
  "content": "This is a test document",
  "metadata": {
    "tenantId": "tenant-fridayfilmhouse",
    "personaId": "test"
  }
}
```

2. **Check each node output** step by step

3. **Find where data stops flowing**

---

## Expected Data at Each Step:

**Prepare Qdrant Point output:**
```json
{
  "id": "uuid-here",
  "vector": [0.123, 0.456, ...],  // 384 numbers
  "collectionName": "tenant-fridayfilmhouse_knowledge",
  "payload": {
    "text": "chunk content",
    "fileName": "test.txt",
    "tenantId": "tenant-fridayfilmhouse",
    ...
  }
}
```

**Prepare JSON output:**
```json
{
  "points": [{
    "id": "uuid-here",
    "vector": [0.123, 0.456, ...],
    "payload": {...}
  }]
}
```

---

## If Still Not Working:

**Share from N8N:**
1. Screenshot of failed execution
2. Error message from any red node
3. Output data from "Prepare JSON" node
4. Output data from "Insert Qdrant" node

This will help identify exactly where it's breaking!
