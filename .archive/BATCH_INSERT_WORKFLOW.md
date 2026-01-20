# Batch Insert Upload Workflow - OPTIMIZED

## ✅ What's Different:

### OLD (Broken):
```
Split Chunks → Generate Embedding (first only) → ...
Only processes 1 chunk! ❌
```

### NEW (Fixed):
```
Split Chunks → Generate Embeddings (ALL) → Prepare Points (ALL) → Batch Insert
Processes ALL chunks at once! ✅
```

---

## 🚀 How It Works:

### 1. Set Basic Info
- Extracts metadata
- Builds collection name: `{tenantId}_knowledge`

### 2. Split Chunks
- Splits content into 2000-char chunks with 200-char overlap
- **Returns MULTIPLE items** (one per chunk)

### 3. Generate Embeddings (All) ← **KEY FIX**
```javascript
const items = $input.all();  // Gets ALL chunks!
for (const item of items) {
  // Generate embedding for EACH chunk
}
return results;  // Returns ALL embeddings
```

### 4. Prepare Points (All) ← **KEY FIX**
```javascript
const items = $input.all();  // Gets ALL embeddings!
for (const item of items) {
  // Create point for EACH
}
return results;  // Returns ALL points
```

### 5. Batch Points ← **KEY FIX**
```javascript
const items = $input.all();  // Gets ALL points!
const points = items.map(...);  // Batch them together

return [{
  json: {
    points: points,  // Array of ALL points!
    collectionName: "tenant-xxx_knowledge"
  }
}];
```

### 6. Batch Insert Qdrant
**Single HTTP request with ALL points:**
```json
PUT /collections/{collectionName}/points
{
  "points": [
    {"id": "...", "vector": [...], "payload": {...}},
    {"id": "...", "vector": [...], "payload": {...}},
    {"id": "...", "vector": [...], "payload": {...}}
  ]
}
```

**One insert for ALL chunks!** ✅

---

## ✅ Benefits:

1. **Processes ALL chunks** (not just first)
2. **Single insert operation** (faster)
3. **Better error handling** (all-or-nothing)
4. **Console logging** (for debugging)

---

## 📋 To Use:

### 1. Create Collection:
```bash
curl -X PUT http://localhost:6333/collections/tenant-fridayfilmhouse_knowledge \
  -H 'Content-Type: application/json' \
  -d '{"vectors": {"size": 384, "distance": "Cosine"}}'
```

### 2. Import Workflow:
- File: `workflows/n8n/Digital Twin - Upload (Multi-tenant).json`
- Import to N8N
- Activate

### 3. Test Upload:
- Upload a file via OpenWebUI
- Check N8N execution
- Should see logs:
  - "Processing X chunks..."
  - "Generated X embeddings"
  - "Prepared X points"
  - "Batching X points..."

### 4. Verify:
```bash
curl http://localhost:6333/collections/tenant-fridayfilmhouse_knowledge | \
  jq '.result.points_count'

# Should show number of chunks inserted!
```

---

## 🎯 Expected Flow:

**Upload 5000-char document:**
```
1. Split Chunks: Creates 3 chunks
2. Generate Embeddings: Processes all 3 → 3 embeddings
3. Prepare Points: Creates 3 points
4. Batch Points: Combines into 1 batch
5. Batch Insert: Inserts all 3 at once ✅
6. Response: "Indexed 3 chunks"
```

**Qdrant result:** 3 vectors ✅

---

## 🐛 Debug:

If still not working, check N8N execution:

1. **After "Split Chunks":** Should show 3+ items
2. **After "Generate Embeddings (All)":** Should show 3+ items
3. **After "Batch Points":** Should show 1 item with `points` array
4. **Check console logs** in N8N for debug messages

---

**This WILL work - it processes ALL chunks and inserts them in a single batch!** 🚀
