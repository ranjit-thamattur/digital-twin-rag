#!/bin/bash
# Complete end-to-end test for S3 upload flow
# This tests: OpenWebUI → Pipeline → S3 → Lambda → N8N → Qdrant

set -e

echo "========================================"
echo "S3 Upload Flow - Complete Test"
echo "========================================"

# Step 1: Create test user in Keycloak (if needed)
echo ""
echo "Step 1: Ensure tenant user exists in Keycloak"
echo "Login to Keycloak: http://localhost:8080/admin"
echo "Create user: alice@tenantA.com with password"
echo "Press Enter when ready..."
read

# Step 2: Test file upload via OpenWebUI
echo ""
echo "Step 2: Upload file via OpenWebUI"
echo "1. Go to: http://localhost:3000"
echo "2. Login with: alice@tenantA.com"
echo "3. Select model: self2ai_rag"
echo "4. Click paperclip icon and upload a text file"
echo "5. You should see: '✅ Uploaded 1 file(s) to S3'"
echo ""
echo "Press Enter after uploading..."
read

# Step 3: Verify S3 storage
echo ""
echo "Step 3: Verifying S3 storage..."
docker exec localstack aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://digital-twin-docs/ --recursive

echo ""
echo "Expected to see: tenant-gmail-com/user/yourfile.txt"
echo "Press Enter to continue..."
read

# Step 4: Check Lambda logs
echo ""
echo "Step 4: Checking Lambda execution..."
docker logs localstack 2>&1 | grep -A 5 "document-processor" | tail -20

echo ""
echo "Expected to see Lambda processing logs"
echo "Press Enter to continue..."
read

# Step 5: Check N8N execution
echo ""
echo "Step 5: Check N8N workflow execution"
echo "Go to: http://localhost:5678"
echo "Click on 'Digital Twin - Upload (Multi-tenant)'"
echo "Click 'Executions' tab - should see recent execution"
echo "Press Enter when verified..."
read

# Step 6: Verify Qdrant indexing
echo ""
echo "Step 6: Checking Qdrant indexing..."

TENANT_FILTER='tenant-gmail-com'  # Adjust based on your email

curl -s -X POST http://localhost:6333/collections/digital_twin_knowledge/points/scroll \
  -H "Content-Type: application/json" \
  -d "{
    \"limit\": 1,
    \"with_payload\": true,
    \"filter\": {
      \"must\": [
        {\"key\": \"tenantId\", \"match\": {\"value\": \"$TENANT_FILTER\"}}
      ]
    }
  }" | jq '.result.points[0].payload'

echo ""
echo "Expected to see: fileName, tenantId, personaId, s3Key, s3Bucket"
echo "Press Enter to continue..."
read

# Step 7: Test RAG chat
echo ""
echo "Step 7: Test RAG chat"
echo "1. In OpenWebUI, ask: 'What is in the document?'"
echo "2. Should get answer based on uploaded file"
echo ""
echo "Press Enter when tested..."
read

echo ""
echo "========================================"
echo "✅ Test Complete!"
echo "========================================"
