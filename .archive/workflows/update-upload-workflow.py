#!/usr/bin/env python3
import json

# Load the workflow
with open('/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/Digital Twin - Upload (Multi-tenant).json', 'r') as f:
    workflow = json.load(f)

# Find and update the "Check & Create Collection" node
for node in workflow['nodes']:
    if node['name'] == 'Check & Create Collection':
        # Update the jsCode
        node['parameters']['jsCode'] = """// Check if collection exists, create if not
const item = $input.first();
const collectionName = item.json.collectionName;

console.log(`Checking if collection ${collectionName} exists...`);

let collectionExists = false;
try {
  const checkResponse = await this.helpers.httpRequest({
    method: 'GET',
    url: `http://qdrant:6333/collections/${collectionName}`,
    json: true
  });
  collectionExists = true;
  console.log(`Collection ${collectionName} exists`);
} catch (error) {
  // 404 means collection doesn't exist - this is expected
  console.log(`Collection ${collectionName} not found, will create it`);
  collectionExists = false;
}

// Create collection if it doesn't exist
if (!collectionExists) {
  console.log(`Creating collection ${collectionName}...`);
  
  const createResponse = await this.helpers.httpRequest({
    method: 'PUT',
    url: `http://qdrant:6333/collections/${collectionName}`,
    body: {
      vectors: {
        size: 768,
        distance: 'Cosine'
      }
    },
    json: true
  });
  
  console.log(`Collection created successfully:`, createResponse);
}

// Pass through original data
return [item];"""
        print("✅ Updated 'Check & Create Collection' node with 768-dim vectors")

# Save the updated workflow
with open('/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/Digital Twin - Upload (Multi-tenant).json', 'w') as f:
    json.dump(workflow, f, indent=2)

print("✅ Upload workflow updated successfully!")
print("")
print("Changes made:")
print("1. Auto-creates Qdrant collections if they don't exist")
print("2. Uses 768-dimensional vectors (matching nomic-embed-text)")
print("3. Uses Cosine distance for similarity")
