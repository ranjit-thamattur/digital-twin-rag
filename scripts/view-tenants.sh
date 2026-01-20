#!/bin/bash
# View Tenants via Tenant Service API

echo "========================================="
echo "Tenant Service - View All Tenants"
echo "========================================="
echo ""

echo "Fetching tenants from API..."
curl -s http://localhost:8000/api/tenants | jq -r '
  if type == "array" then
    .[] | 
    "
Tenant ID:       \(.tenant_id)
Company Name:    \(.company_name)
Industry:        \(.industry)
Tone:            \(.tone)
Active:          \(.is_active)
Created:         \(.created_at)
----------------------------------------
"
  else
    .
  end
'

echo ""
echo "========================================="
echo "Quick Summary"
echo "========================================="
curl -s http://localhost:8000/api/tenants | jq -r '
  if type == "array" then
    "Total Tenants: \(length)",
    "",
    "Tenant List:",
    (.[] | "  • \(.company_name) (\(.tenant_id))")
  else
    .
  end
'

echo ""
echo "Done!"
