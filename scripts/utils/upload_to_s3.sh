#!/bin/bash
# S3 Upload Helper for LocalStack
# Fixes AWS CLI compatibility issues

LOCALSTACK_URL="http://localhost:4566"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "📤 S3 Upload Helper for LocalStack"
echo "=================================="
echo ""

# Check if file is provided
if [ -z "$1" ]; then
    echo "Usage: ./upload_to_s3.sh <file> <tenant-id> <persona-id>"
    echo ""
    echo "Example:"
    echo "  ./upload_to_s3.sh test.txt tenant-123 persona-user"
    echo "  ./upload_to_s3.sh report.pdf tenant-acme CEO"
    echo ""
    exit 1
fi

FILE=$1
TENANT=${2:-"tenant-123"}
PERSONA=${3:-"persona-user"}

# Extract filename
FILENAME=$(basename "$FILE")

# Build S3 path
S3_PATH="$TENANT/$PERSONA/files/$FILENAME"
S3_URI="s3://digital-twin-files/$S3_PATH"

echo "File: $FILE"
echo "Tenant: $TENANT"
echo "Persona: $PERSONA"
echo "S3 Path: $S3_PATH"
echo ""

# Method 1: Try AWS CLI without --no-progress (works better with LocalStack)
echo "Attempting upload (Method 1: Standard AWS CLI)..."
if aws --endpoint-url=${LOCALSTACK_URL} s3 cp "$FILE" "$S3_URI" 2>&1 | grep -q "upload:"; then
    echo -e "${GREEN}✅ Upload successful!${NC}"
    echo ""
    echo "Verify:"
    echo "  aws --endpoint-url=${LOCALSTACK_URL} s3 ls s3://digital-twin-files/$TENANT/$PERSONA/files/"
    exit 0
fi

# Method 2: Try with explicit content-type
echo ""
echo "Method 1 failed. Trying Method 2: With explicit content-type..."
CONTENT_TYPE="text/plain"
if [[ "$FILE" == *.pdf ]]; then
    CONTENT_TYPE="application/pdf"
elif [[ "$FILE" == *.txt ]]; then
    CONTENT_TYPE="text/plain"
fi

if aws --endpoint-url=${LOCALSTACK_URL} s3 cp "$FILE" "$S3_URI" \
    --content-type "$CONTENT_TYPE" 2>&1 | grep -q "upload:"; then
    echo -e "${GREEN}✅ Upload successful!${NC}"
    exit 0
fi

# Method 3: Use Python boto3 directly
echo ""
echo "Methods 1-2 failed. Trying Method 3: Python boto3..."

python3 << PYTHON_SCRIPT
import boto3
import sys

try:
    s3 = boto3.client('s3', endpoint_url='${LOCALSTACK_URL}')
    
    with open('${FILE}', 'rb') as f:
        s3.put_object(
            Bucket='digital-twin-files',
            Key='${S3_PATH}',
            Body=f.read()
        )
    
    print('${GREEN}✅ Upload successful!${NC}')
    sys.exit(0)
except Exception as e:
    print(f'${RED}❌ Upload failed: {e}${NC}')
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo "Verify:"
    echo "  aws --endpoint-url=${LOCALSTACK_URL} s3 ls s3://digital-twin-files/$TENANT/$PERSONA/files/"
    exit 0
fi

# Method 4: Use curl
echo ""
echo "All methods failed. Trying Method 4: Direct HTTP..."

# This is a last resort - create presigned URL approach would go here
echo -e "${RED}❌ All upload methods failed${NC}"
echo ""
echo "Troubleshooting:"
echo "1. Check LocalStack is running:"
echo "   docker-compose ps localstack"
echo ""
echo "2. Check LocalStack health:"
echo "   curl http://localhost:4566/_localstack/health"
echo ""
echo "3. Check LocalStack logs:"
echo "   docker-compose logs localstack | tail -50"
echo ""
exit 1
