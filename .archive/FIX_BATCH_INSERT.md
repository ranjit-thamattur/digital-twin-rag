# Debug: Why Points Aren't Inserting

## Check N8N Execution Details

### In N8N UI:
1. Open the workflow execution
2. Check EACH node's output
3. Count the items at each step

### Expected vs Actual:

**Expected Flow (for a 5000-char document):**
```
Split Chunks: 3 items (3 chunks)
  ↓
Generate Embedding: 3 executions → 3 items
  ↓
Prepare Qdrant Point: 3 executions → 3 items
  ↓
Prepare JSON: 3 executions → 3 items
  ↓
Insert Qdrant: 3 executions → 3 inserts
```

**Actual (Probably):**
```
Split Chunks: 3 items ✅
  ↓
Generate Embedding: 1 execution → 1 item ❌ (stops here!)
  ↓
Prepare Qdrant Point: 1 execution → 1 item
  ↓  
Insert Qdrant: 1 execution → 1 insert (acknowledged but fails)
```

---

## Root Cause: N8N Execution Mode

**Code nodes using `$input.first()`** only process the FIRST item!

### Broken Nodes:
- `Generate Embedding`: Uses `$input.first()`
- `Prepare Qdrant Point`: Uses `$input.first()`
- `Prepare JSON`: Uses `$input.first()`

**This means only 1 chunk gets processed!**

---

## ✅ Fix: Process ALL Items

Change code nodes to process all items in a loop:

### Fixed "Generate Embedding":
```javascript
const items = $input.all();
const results = [];

for (const item of items) {
  const text = item.json.text || '';
  const cleanedText = text.replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim();
  
  const response = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://ollama:11434/api/embeddings',
    body: { model: 'nomic-embed-text', prompt: cleanedText },
    json: true
  });
  
  results.push({
    json: {
      embedding: response.embedding,
      text: item.json.text,
      fileName: item.json.fileName,
      chunkIndex: item.json.chunkIndex,
      uploadDate: item.json.uploadDate,
      tenantId: item.json.tenantId,
      personaId: item.json.personaId,
      s3Key: item.json.s3Key,
      s3Bucket: item.json.s3Bucket,
      collectionName: item.json.collectionName
    }
  });
}

return results;
```

### Fixed "Prepare Qdrant Point":
```javascript
const items = $input.all();
const results = [];

function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

for (const item of items) {
  results.push({
    json: {
      id: generateUUID(),
      vector: item.json.embedding,
      collectionName: item.json.collectionName,
      payload: {
        text: item.json.text,
        fileName: item.json.fileName,
        chunkIndex: item.json.chunkIndex,
        uploadDate: item.json.uploadDate,
        tenantId: item.json.tenantId,
        personaId: item.json.personaId,
        s3Key: item.json.s3Key,
        s3Bucket: item.json.s3Bucket
      }
    }
  });
}

return results;
```

### Fixed "Prepare JSON":
```javascript
const items = $input.all();

// Collect all points
const points = items.map(item => ({
  id: item.json.id,
  vector: item.json.vector,
  payload: item.json.payload
}));

// Get collection name from first item
const collectionName = items[0]?.json.collectionName;

return [{
  json: {
    points: points,
    collectionName: collectionName
  }
}];
```

### Fixed "Insert Qdrant":
```javascript
// URL should use collectionName from input
http://qdrant:6333/collections/{{$json.collectionName}}/points
```

---

## Quick Test in N8N:

### Add Debug Node After "Split Chunks":
```javascript
const items = $input.all();
console.log(`Split Chunks created ${items.length} items`);
return items;
```

**Check output:** Should show multiple items!

---

## Alternative: Batch Insert

Instead of looping, insert ALL chunks at once:

**"Prepare JSON" batches all chunks:**
```javascript
const items = $input.all();

const points = items.map(item => ({
  id: item.json.id,
  vector: item.json.vector,
  payload: item.json.payload
}));

return [{
  json: {
    points: points  // Array of ALL chunks!
  }
}];
```

**Then "Insert Qdrant" inserts all at once** → Much faster!

---

## Summary:

**Problem:** `$input.first()` only processes 1 item  
**Solution:** Use `$input.all()` and loop through items  
**Better:** Batch all chunks into one insert operation

Want me to create the fixed workflow with batch insert?
