#!/bin/bash
# Upload Mastro Metals Inventory to N8N

# Source tenant ID
if [ -f /tmp/mastro-tenant-id.sh ]; then
  source /tmp/mastro-tenant-id.sh
else
  echo "⚠️  Tenant ID not found. Please run create-mastro-metals-tenant.sh first"
  echo "Or set MASTRO_TENANT_ID manually:"
  echo "export MASTRO_TENANT_ID=tenant-mastrometals"
  exit 1
fi

echo "🏭 Uploading Mastro Metals Inventory..."
echo "Tenant ID: $MASTRO_TENANT_ID"
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
    "tenantId": "$MASTRO_TENANT_ID",
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
else
  echo "❌ Upload failed!"
fi
