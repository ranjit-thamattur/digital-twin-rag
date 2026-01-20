#!/bin/bash
# Test queries for Mastro Metals

# Source tenant ID
if [ -f /tmp/mastro-tenant-id.sh ]; then
  source /tmp/mastro-tenant-id.sh
else
  echo "⚠️  Using default tenant ID"
  MASTRO_TENANT_ID="tenant-mastrometals"
fi

echo "🧪 Testing Mastro Metals RAG Queries..."
echo "Tenant ID: $MASTRO_TENANT_ID"
echo ""

# Test Query 1: Check MS pipe stock
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query 1: What MS pipes do you have in 2 inch size?"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d "{
  \"message\": \"What MS pipes do you have in 2 inch size? Give me stock and price.\",
  \"tenantId\": \"$MASTRO_TENANT_ID\",
  \"personaId\": \"Sales Manager\"
}" | jq '.'
echo ""
echo ""

# Test Query 2: GI pipe pricing
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query 2: What is the price of GI pipes?"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d "{
  \"message\": \"What is the price range for GI medium class pipes?\",
  \"tenantId\": \"$MASTRO_TENANT_ID\",
  \"personaId\": \"Sales Manager\"
}" | jq '.'
echo ""
echo ""

# Test Query 3: Bulk discount
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query 3: What discounts do you offer for bulk orders?"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d "{
  \"message\": \"What discounts do you offer for bulk orders of 500 pieces?\",
  \"tenantId\": \"$MASTRO_TENANT_ID\",
  \"personaId\": \"Sales Manager\"
}" | jq '.'
echo ""
echo ""

# Test Query 4: SS pipes
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Query 4: Tell me about stainless steel pipes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
curl -X POST http://localhost:5678/webhook/openwebui \
-H "Content-Type: application/json" \
-d "{
  \"message\": \"What stainless steel pipes do you have? I need 1 inch size.\",
  \"tenantId\": \"$MASTRO_TENANT_ID\",
  \"personaId\": \"Sales Manager\"
}" | jq '.'
echo ""
