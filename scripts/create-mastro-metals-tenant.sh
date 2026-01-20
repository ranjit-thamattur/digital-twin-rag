#!/bin/bash
# Create Mastro Metals Dealers Tenant

echo "🏭 Creating Mastro Metals Dealers Tenant..."
echo ""

# Create tenant
TENANT_RESPONSE=$(curl -s -X POST http://localhost:3002/api/tenants \
-H "Content-Type: application/json" \
-d '{
  "name": "Mastro Metals Dealers",
  "domain": "mastrometals.com",
  "settings": {
    "industry": "Metal Pipe Distribution",
    "location": "Industrial Estate, Mumbai",
    "business_type": "B2B Wholesale"
  },
  "specialInstructions": "You are an AI assistant for Mastro Metals Dealers, a leading pipe and metal distribution company. You have access to our complete inventory of MS pipes, GI pipes, SS pipes, and other metal products. Always provide accurate stock information, prices, and specifications. Be professional and technical in your responses."
}')

echo "Tenant Response:"
echo "$TENANT_RESPONSE" | jq '.'
echo ""

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.id')

if [ "$TENANT_ID" != "null" ] && [ -n "$TENANT_ID" ]; then
  echo "✅ Tenant created successfully!"
  echo "Tenant ID: $TENANT_ID"
  echo ""
  
  # Save tenant ID for later use
  echo "export MASTRO_TENANT_ID=$TENANT_ID" > /tmp/mastro-tenant-id.sh
  
  echo "📋 Next steps:"
  echo "1. Create users for this tenant (optional)"
  echo "2. Upload inventory documents"
  echo "3. Test queries"
else
  echo "❌ Failed to create tenant"
  exit 1
fi
