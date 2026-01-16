#!/bin/bash
# Create Qdrant Indexes for Multi-tenant Vector Search
# Run this after starting Qdrant

set -e

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="digital_twin_knowledge"

echo "🔍 Setting up Qdrant Indexes for Multi-tenant Search"
echo "======================================================"
echo ""
echo "Qdrant URL: $QDRANT_URL"
echo "Collection: $COLLECTION"
echo ""

# Wait for Qdrant to be ready
echo "⏳ Waiting for Qdrant to start..."
until curl -s ${QDRANT_URL}/collections | grep -q "collections"; do
    echo "   Waiting for Qdrant..."
    sleep 2
done
echo "✅ Qdrant is ready!"
echo ""

# Check if collection exists, create if not
echo "📦 Checking collection: $COLLECTION"
if ! curl -s ${QDRANT_URL}/collections/${COLLECTION} | grep -q "\"status\":\"green\|yellow\""; then
    echo "   Creating collection..."
    curl -X PUT ${QDRANT_URL}/collections/${COLLECTION} \
      -H "Content-Type: application/json" \
      -d '{
        "vectors": {
          "size": 768,
          "distance": "Cosine"
        }
      }' > /dev/null 2>&1
    echo "✅ Collection created"
else
    echo "✅ Collection already exists"
fi
echo ""

# Create index for tenantId
echo "🔑 Creating index: tenantId"
curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "tenantId",
    "field_schema": "keyword"
  }' > /dev/null 2>&1
echo "✅ Index created: tenantId"
echo ""

# Create index for personaId
echo "🔑 Creating index: personaId"
curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "personaId",
    "field_schema": "keyword"
  }' > /dev/null 2>&1
echo "✅ Index created: personaId"
echo ""

# Create index for fileName
echo "🔑 Creating index: fileName"
curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "fileName",
    "field_schema": "keyword"
  }' > /dev/null 2>&1
echo "✅ Index created: fileName"
echo ""

# Create index for s3Key
echo "🔑 Creating index: s3Key"
curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "s3Key",
    "field_schema": "keyword"
  }' > /dev/null 2>&1
echo "✅ Index created: s3Key"
echo ""

# Verify collection info
echo "📊 Collection Info:"
curl -s ${QDRANT_URL}/collections/${COLLECTION} | jq '{
  status: .result.status,
  vectors_count: .result.points_count,
  indexed_vectors_count: .result.indexed_vectors_count,
  payload_schema: .result.payload_schema
}'
echo ""

echo "✅ All indexes created successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 USAGE EXAMPLES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  Search by tenant only:"
echo "   curl -X POST ${QDRANT_URL}/collections/${COLLECTION}/points/search \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"vector\":[...],\"filter\":{\"must\":[{\"key\":\"tenantId\",\"match\":{\"value\":\"tenant-123\"}}]},\"limit\":5}'"
echo ""
echo "2️⃣  Search by tenant + persona:"
echo "   curl -X POST ${QDRANT_URL}/collections/${COLLECTION}/points/search \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"vector\":[...],\"filter\":{\"must\":[{\"key\":\"tenantId\",\"match\":{\"value\":\"tenant-123\"}},{\"key\":\"personaId\",\"match\":{\"value\":\"persona-user\"}}]},\"limit\":5}'"
echo ""
echo "3️⃣  List all tenants:"
echo "   curl -s ${QDRANT_URL}/collections/${COLLECTION}/points/scroll \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"limit\":100,\"with_payload\":true,\"with_vector\":false}' | jq '.result.points[].payload.tenantId' | sort -u"
echo ""
echo "4️⃣  Count documents per tenant:"
echo "   curl -s ${QDRANT_URL}/collections/${COLLECTION}/points/scroll \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"limit\":1000,\"with_payload\":true,\"with_vector\":false}' | jq '.result.points[].payload.tenantId' | sort | uniq -c"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
