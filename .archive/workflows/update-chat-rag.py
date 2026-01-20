#!/usr/bin/env python3
import json

# Load the workflow
with open('/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/Digital Twin - Chat RAG (Multi-tenant).json', 'r') as f:
    workflow = json.load(f)

# Find and update the "Build Search" node
for node in workflow['nodes']:
    if node['name'] == 'Build Search':
        # Update the jsCode
        node['parameters']['jsCode'] = """// Build Search with Tenant/Persona Filtering
const item = $input.first();
const embedResponse = item.json;
const extractNode = $('Extract Query').first();
const query = extractNode.json.query;
const tenantId = extractNode.json.tenantId;
const personaId = extractNode.json.personaId;

let embedding = embedResponse.embedding;

if (!embedding || !Array.isArray(embedding) || embedding.length === 0) {
  return [{ json: { error: 'No embedding' } }];
}

// Build filter
const filter = { must: [] };
if (tenantId) {
  filter.must.push({ key: 'tenantId', match: { value: tenantId } });
}
if (personaId) {
  filter.must.push({ key: 'personaId', match: { value: personaId } });
}

// Build collection name from tenantId
const collectionName = tenantId ? `${tenantId}_knowledge` : 'digital_twin_knowledge';

return [{
  json: {
    vector: embedding,
    filter: filter.must.length > 0 ? filter : undefined,
    limit: 5,
    with_payload: true,
    with_vector: false,
    query,
    tenantId,
    personaId,
    collectionName
  }
}];"""
        print("✅ Updated 'Build Search' node")

# Save the updated workflow
with open('/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/Digital Twin - Chat RAG (Multi-tenant).json', 'w') as f:
    json.dump(workflow, f, indent=2)

print("✅ Chat RAG workflow updated successfully!")
print("")
print("Changes made:")
print("1. Added 'collectionName' calculation in Build Search node")
print("2. Search Qdrant URL is already dynamic: =http://qdrant:6333/collections/{{$json.collectionName}}/points/search")
