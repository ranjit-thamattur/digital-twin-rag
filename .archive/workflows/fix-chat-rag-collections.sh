#!/bin/bash
# Update Chat RAG workflow to use dynamic collection names

WORKFLOW_FILE="/Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/Digital Twin - Chat RAG (Multi-tenant).json"

echo "Updating Chat RAG workflow for dynamic collections..."

# 1. Update Build Search to include collectionName
# 2. Update Search Qdrant URL to use collectionName

# Make backup
cp "$WORKFLOW_FILE" "$WORKFLOW_FILE.bak"

# Update the URL to be dynamic
sed -i '' 's|http://qdrant:6333/collections/digital_twin_knowledge/points/search|=http://qdrant:6333/collections/{{$json.collectionName}}/points/search|g' "$WORKFLOW_FILE"

echo "✅ Updated Search Qdrant URL to be dynamic"
echo ""
echo "⚠️  MANUAL STEP REQUIRED:"
echo "Open the 'Build Search' node in N8N and add this line before the return statement:"
echo ""
echo "const collectionName = tenantId ? \`\${tenantId}_knowledge\` : 'digital_twin_knowledge';"
echo ""
echo "And add 'collectionName' to the return json object."
