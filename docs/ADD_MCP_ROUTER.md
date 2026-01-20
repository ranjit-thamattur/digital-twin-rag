# Adding MCP Model Router to Chat RAG Workflow

## What This Does
Intelligently selects the best LLM model based on query complexity:
- **llama3.2:1b** (fast, 3-5s) → Simple queries: "What price?", "Do you have?"
- **llama3.2:latest** (medium, 20s) → Comparisons: "Compare X and Y", "Which is better?"
- **phi3:mini** (slow, 30s+) → Complex: "Calculate", "Why", "Optimize"

---

## Implementation Steps

### 1. Add New Node in N8N

Open: **Digital Twin - Chat RAG (Multi-tenant)** workflow

**Add a new Code node** between "Build Search" and "Build Prompt":

**Position:** After "Search Qdrant", before "Build Prompt"

**Node Name:** `MCP Model Router`

**Code:** Copy from `/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/mcp-model-router.js`

---

### 2. Update "Generate Answer" Node

Change the model field from hardcoded to dynamic:

**Before:**
```json
"model": "llama3.2:1b"
```

**After:**
```json
"model": "={{$json.selectedModel}}"
```

Or in the N8N expression editor:
```
{{$json.selectedModel}}
```

---

### 3. Updated Workflow Flow

```
Webhook
  → Extract Query
  → Check Skip
  → Embed Query
  → Build Search
  → Search Qdrant
  → MCP Model Router    ← NEW!
  → Build Prompt
  → Generate Answer     ← Uses {{$json.selectedModel}}
  → Extract Response
```

---

## Test Examples

### Simple Query (→ llama3.2:1b, ~3-5s):
```bash
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d '{
  "message": "What 2 inch MS pipes do you have?",
  "tenantId": "tenant-mastrometals"
}'
```

### Medium Query (→ llama3.2:latest, ~20s):
```bash
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d '{
  "message": "Compare GI and MS pipes for outdoor use",
  "tenantId": "tenant-mastrometals"
}'
```

### Complex Query (→ phi3:mini, ~30s):
```bash
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d '{
  "message": "Calculate the total cost for 500 pieces of 2 inch MS pipes with bulk discount",
  "tenantId": "tenant-mastrometals"
}'
```

---

## Benefits

✅ **Optimized Speed**: 90% of queries use fast model  
✅ **Better Quality**: Complex queries get smart model  
✅ **Cost Efficient**: Less compute for simple tasks  
✅ **Transparent**: Logs show why each model was chosen  

---

## Monitoring

Check N8N execution logs to see:
- Which model was selected
- Selection reason
- Query complexity scores

Example log:
```
Selected model: llama3.2:1b
Reason: Simple query - using fast model
Query scores: { simple: 2, medium: 0, complex: 0 }
```

---

## Customization

Edit `mcp-model-router.js` to:
- Add more keywords/patterns
- Adjust scoring weights
- Add tenant-specific rules
- Include time-of-day routing (off-peak = slower models OK)
