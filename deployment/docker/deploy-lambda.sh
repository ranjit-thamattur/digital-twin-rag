#!/bin/bash
# Deploy Lambda function and configure S3 event trigger in LocalStack

set -e

echo "Deploying document-processor Lambda..."

# Set LocalStack endpoint
ENDPOINT="http://localhost:4566"

# Package Lambda function
cd lambda/document-processor
zip -r function.zip index.py
cd ../..

# Create Lambda function
aws --endpoint-url=$ENDPOINT lambda create-function \
  --function-name document-processor \
  --runtime python3.11 \
  --handler index.lambda_handler \
  --zip-file fileb://lambda/document-processor/function.zip \
  --role arn:aws:iam::000000000000:role/lambda-role \
  --timeout 300 \
  --memory-size 512 \
  2>/dev/null || echo "Lambda function already exists, updating..."

# Update Lambda if it exists
aws --endpoint-url=$ENDPOINT lambda update-function-code \
  --function-name document-processor \
  --zip-file fileb://lambda/document-processor/function.zip \
  2>/dev/null || true

echo "Configuring S3 event notification..."

# Create notification configuration
cat > /tmp/s3-notification.json <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:document-processor",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
EOF

# Set bucket notification
aws --endpoint-url=$ENDPOINT s3api put-bucket-notification-configuration \
  --bucket digital-twin-docs \
  --notification-configuration file:///tmp/s3-notification.json

echo "✅ Lambda deployed and S3 trigger configured!"
echo ""
echo "Test with:"
echo "  aws --endpoint-url=$ENDPOINT s3 cp test.txt s3://digital-twin-docs/tenantA/CEO/test.txt"
