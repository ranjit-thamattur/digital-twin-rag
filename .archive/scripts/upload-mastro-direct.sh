#!/bin/bash
# Direct Upload for Mastro Metals (No tenant service needed)

TENANT_ID="tenant-mastrometals"

echo "🏭 Uploading Mastro Metals Inventory..."
echo "Tenant ID: $TENANT_ID"
echo ""

# Read the inventory file
INVENTORY_CONTENT=$(cat /Users/ranjitt/Ranjit/digital-twin-rag/data/mastro-metals-inventory.txt)

# Upload to N8N
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:5678/webhook/upload-document \
-H "Content-Type: application/json" \
-d @- << EOF
{
  "fileName": "Mastro_Metals_Pipe_Inventory.txt",
  "content": $(echo "$INVENTORY_CONTENT" | jq -Rs .),
  "metadata": {
    "tenantId": "$TENANT_ID",
    "personaId": "Sales Manager"
  }
}
EOF
)

echo "Upload Response:"
echo "$UPLOAD_RESPONSE" | jq '.'
echo ""

# Check if successful
SUCCESS=$(echo "$UPLOAD_RESPONSE" | jq -r '.[0].success // false')

if [ "$SUCCESS" = "true" ]; then
  CHUNKS=$(echo "$UPLOAD_RESPONSE" | jq -r '.[0].chunksIndexed')
  COLLECTION=$(echo "$UPLOAD_RESPONSE" | jq -r '.[0].collectionName')
  
  echo "✅ Upload successful!"
  echo "Chunks indexed: $CHUNKS"
  echo "Collection: $COLLECTION"
  echo ""
  echo "📊 Verify in Qdrant:"
  echo "curl -s 'http://localhost:6333/collections/$COLLECTION' | jq '.result.points_count'"
  echo ""
  echo "🧪 Test a query:"
  echo "chmod +x /Users/ranjitt/Ranjit/digital-twin-rag/scripts/test-mastro-queries.sh"
  echo "/Users/ranjitt/Ranjit/digital-twin-rag/scripts/test-mastro-queries.sh"
else
  echo "❌ Upload failed!"
  echo "$UPLOAD_RESPONSE"
fi
