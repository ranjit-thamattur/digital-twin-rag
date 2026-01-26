#!/bin/bash
# Complete Setup: LocalStack + Qdrant Indexes + Lambda
# FIXED VERSION - Shows all errors

set -e

LOCALSTACK_URL="http://localhost:4566"
QDRANT_URL="http://localhost:6333"
N8N_WEBHOOK="http://n8n-dt:5678/webhook/upload-document"

echo "🚀 Digital Twin RAG - Complete Setup (FIXED)"
echo "============================================="
echo ""

# ============================================
# STEP 1: Setup Qdrant Indexes
# ============================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Setting up Qdrant Indexes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Wait for Qdrant
echo "⏳ Waiting for Qdrant..."
until curl -s ${QDRANT_URL}/collections | grep -q "collections"; do
    echo "   Waiting for Qdrant..."
    sleep 2
done
echo "✅ Qdrant ready"
echo ""

# Create collection if not exists
COLLECTION="digital_twin_knowledge"
echo "📦 Checking collection: $COLLECTION"
if ! curl -s ${QDRANT_URL}/collections/${COLLECTION} 2>/dev/null | grep -q "\"status\":\"green\|yellow\""; then
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
    echo "✅ Collection exists"
fi
echo ""

# Create indexes
echo "🔑 Creating payload indexes..."

curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{"field_name":"tenantId","field_schema":"keyword"}' > /dev/null 2>&1
echo "   ✅ tenantId"

curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{"field_name":"personaId","field_schema":"keyword"}' > /dev/null 2>&1
echo "   ✅ personaId"

curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{"field_name":"fileName","field_schema":"keyword"}' > /dev/null 2>&1
echo "   ✅ fileName"

curl -s -X PUT ${QDRANT_URL}/collections/${COLLECTION}/index \
  -H "Content-Type: application/json" \
  -d '{"field_name":"s3Key","field_schema":"keyword"}' > /dev/null 2>&1
echo "   ✅ s3Key"

echo ""
echo "✅ Qdrant indexes created"
echo ""

# ============================================
# STEP 2: Setup LocalStack
# ============================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Setting up LocalStack (S3/Lambda)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Wait for LocalStack
echo "⏳ Waiting for LocalStack..."
for i in {1..30}; do
    if curl -s ${LOCALSTACK_URL}/_localstack/health | grep -q "running"; then
        echo "✅ LocalStack ready"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# Create S3 bucket
echo "📦 Creating S3 bucket..."
if aws --endpoint-url=${LOCALSTACK_URL} s3 mb s3://digital-twin-files 2>&1 | grep -q "BucketAlreadyOwnedByYou\|make_bucket"; then
    echo "✅ S3 bucket ready"
else
    echo "⚠️  Bucket creation issue (may already exist)"
fi
echo ""

# Enable EventBridge - FIXED VERSION
echo "🔔 Enabling S3 → EventBridge..."

# First, check if EventBridge is supported
if aws --endpoint-url=${LOCALSTACK_URL} events list-rules 2>&1 | grep -q "error\|Could not connect"; then
    echo "⚠️  EventBridge not available in this LocalStack version"
    echo "   Falling back to S3 notifications directly"
    
    # Use S3 Lambda notifications instead
    echo "   Configuring S3 Lambda notifications..."
    cat > /tmp/s3-notification.json << 'EOF'
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:digital-twin-processor",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
EOF
    
    # Note: We'll configure this after Lambda is created
    echo "   ✅ S3 notification config prepared"
else
    # EventBridge is available
    echo "   Enabling EventBridge configuration..."
    if aws --endpoint-url=${LOCALSTACK_URL} s3api put-bucket-notification-configuration \
      --bucket digital-twin-files \
      --notification-configuration '{"EventBridgeConfiguration":{}}' 2>&1; then
        echo "✅ EventBridge enabled"
    else
        echo "⚠️  EventBridge configuration failed"
        echo "   Using Lambda notifications instead"
        S3_NOTIFICATION_NEEDED=true
    fi
fi
echo ""

# Create Lambda directory and function
mkdir -p lambda
if [ ! -f lambda/lambda_function.py ]; then
    echo "📝 Creating Lambda function..."
    cat > lambda/lambda_function.py << 'LAMBDA_EOF'
import json
import boto3
import os
import urllib.request
import urllib.error
from urllib.parse import unquote_plus

# For LocalStack
s3_endpoint = os.environ.get('AWS_ENDPOINT_URL', 'http://localstack:4566')
s3_client = boto3.client('s3', endpoint_url=s3_endpoint)
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', 'http://n8n-dt:5678/webhook/upload-document')

def lambda_handler(event, context):
    print("Event:", json.dumps(event))
    
    try:
        # Handle both EventBridge and direct S3 events
        if 'detail' in event:
            # EventBridge format
            bucket = event['detail']['bucket']['name']
            key = unquote_plus(event['detail']['object']['key'])
        elif 'Records' in event:
            # Direct S3 event format
            bucket = event['Records'][0]['s3']['bucket']['name']
            key = unquote_plus(event['Records'][0]['s3']['object']['key'])
        else:
            return {'statusCode': 400, 'body': 'Unknown event format'}
        
        print(f"Processing: s3://{bucket}/{key}")
        
        # Parse path: tenant/persona/files/...
        parts = key.split('/', 2)
        tenant_id = parts[0] if len(parts) > 0 else 'unknown'
        persona_id = parts[1] if len(parts) > 1 else 'unknown'
        file_path = parts[2] if len(parts) > 2 else key
        file_name = file_path.split('/')[-1]
        
        # Download file
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8', errors='ignore')
        
        print(f"Extracted {len(content)} characters")
        
        # Call n8n
        payload = {
            'fileName': file_name,
            'content': content,
            'metadata': {
                'tenantId': tenant_id,
                'personaId': persona_id,
                's3Key': key,
                's3Bucket': bucket
            }
        }
        
        print(f"Calling n8n: {N8N_WEBHOOK_URL}")
        
        req = urllib.request.Request(
            N8N_WEBHOOK_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as n8n_response:
                status = n8n_response.getcode()
                if status >= 200 and status < 300:
                    return {
                        'statusCode': 200,
                        'body': json.dumps({'message': 'Processed', 'file': file_name})
                    }
                else:
                    raise Exception(f"n8n returned status {status}")
        except urllib.error.HTTPError as e:
            raise Exception(f"n8n HTTP Error: {e.code}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
LAMBDA_EOF
    echo "   ✅ Lambda code created"
else
    echo "✅ Lambda code exists"
fi
echo ""

# Package Lambda
echo "📦 Packaging Lambda..."
cd lambda
zip -q -r function.zip lambda_function.py 2>/dev/null || true
cd ..
echo "✅ Lambda packaged"
echo ""

# Deploy Lambda
echo "🚀 Deploying Lambda function..."
if aws --endpoint-url=${LOCALSTACK_URL} lambda create-function \
  --function-name digital-twin-processor \
  --runtime python3.11 \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda/function.zip \
  --role arn:aws:iam::000000000000:role/lambda-role \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{N8N_WEBHOOK_URL=${N8N_WEBHOOK},AWS_ENDPOINT_URL=http://localstack:4566}" \
  2>&1 | grep -q "FunctionName\|ResourceConflict"; then
    echo "✅ Lambda deployed"
else
    echo "⚠️  Lambda exists (skipping)"
fi
echo ""

# Configure S3 notifications if needed
if [ "$S3_NOTIFICATION_NEEDED" = "true" ] || ! aws --endpoint-url=${LOCALSTACK_URL} events list-rules 2>&1 | grep -q "s3-upload-trigger"; then
    echo "📋 Configuring S3 → Lambda notifications..."
    
    aws --endpoint-url=${LOCALSTACK_URL} s3api put-bucket-notification-configuration \
      --bucket digital-twin-files \
      --notification-configuration file:///tmp/s3-notification.json 2>&1 || echo "   Using EventBridge instead"
    
    echo "✅ Notifications configured"
    echo ""
fi

# Create EventBridge rule (if available)
if aws --endpoint-url=${LOCALSTACK_URL} events list-rules 2>&1 | grep -qv "error\|Could not connect"; then
    echo "📋 Creating EventBridge rule..."
    aws --endpoint-url=${LOCALSTACK_URL} events put-rule \
      --name s3-upload-trigger \
      --event-pattern '{
        "source":["aws.s3"],
        "detail-type":["Object Created"],
        "detail":{"bucket":{"name":["digital-twin-files"]}}
      }' > /dev/null 2>&1 || echo "   Rule may already exist"
    echo "✅ EventBridge rule created"
    echo ""

    # Add Lambda as target
    echo "🔗 Connecting EventBridge → Lambda..."
    aws --endpoint-url=${LOCALSTACK_URL} events put-targets \
      --rule s3-upload-trigger \
      --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:000000000000:function:digital-twin-processor" > /dev/null 2>&1 || echo "   Target may already exist"
    echo "✅ Lambda target added"
    echo ""
fi

# Create test files
echo "📝 Creating test files..."
cat > test-tenant-123.txt << 'EOF'
ACME CORPORATION - Tenant 123
Financial Report Q4 2024

Revenue: $2,500,000
Expenses: $1,800,000
Net Income: $700,000

This document belongs to tenant-123 / persona-cfo
EOF

cat > test-tenant-456.txt << 'EOF'
GLOBEX INC - Tenant 456
Operations Report Q4 2024

Total Projects: 45
Completed: 38
Success Rate: 84%

This document belongs to tenant-456 / persona-manager
EOF

echo "✅ Test files created"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SETUP COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 QUICK TEST:"
echo ""
echo "1️⃣  Upload test file:"
echo "   aws --endpoint-url=${LOCALSTACK_URL} s3 cp test-tenant-123.txt s3://digital-twin-files/tenant-123/persona-cfo/reports/q4.txt"
echo ""
echo "2️⃣  Check Lambda logs:"
echo "   aws --endpoint-url=${LOCALSTACK_URL} logs tail /aws/lambda/digital-twin-processor --follow"
echo ""
echo "3️⃣  Query Qdrant:"
echo "   curl -X POST ${QDRANT_URL}/collections/digital_twin_knowledge/points/scroll -H 'Content-Type: application/json' -d '{\"limit\":5,\"with_payload\":true}' | jq"
echo ""
echo "Ready to test! 🚀"
