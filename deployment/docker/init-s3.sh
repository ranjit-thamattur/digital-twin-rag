#!/bin/bash
# S3 Bucket Initialization Script for LocalStack
# Creates the digital-twin-docs bucket with versioning enabled

set -e

echo "Waiting for LocalStack to be ready..."
sleep 5

# Set LocalStack endpoint
ENDPOINT="http://localhost:4566"

echo "Creating S3 bucket: digital-twin-docs"
aws --endpoint-url=$ENDPOINT s3 mb s3://digital-twin-docs 2>/dev/null || echo "Bucket already exists"

echo "Enabling versioning on digital-twin-docs"
aws --endpoint-url=$ENDPOINT s3api put-bucket-versioning \
  --bucket digital-twin-docs \
  --versioning-configuration Status=Enabled

echo "Listing buckets:"
aws --endpoint-url=$ENDPOINT s3 ls

echo "S3 initialization complete!"
