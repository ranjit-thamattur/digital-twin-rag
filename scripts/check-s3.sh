#!/bin/bash
# Quick S3 verification script

echo "=========================================="
echo "Checking S3 Bucket Contents"
echo "=========================================="

# List all files in S3 bucket
echo ""
echo "All files in digital-twin-docs bucket:"
docker exec localstack aws --endpoint-url=http://localhost:4566 \
  s3 ls s3://digital-twin-docs/ --recursive

echo ""
echo "=========================================="
echo "Download a specific file (example):"
echo "=========================================="
echo ""
echo "Replace TENANT/PERSONA/FILE with actual path:"
echo "docker exec localstack aws --endpoint-url=http://localhost:4566 \\"
echo "  s3 cp s3://digital-twin-docs/TENANT/PERSONA/FILE.txt -"
