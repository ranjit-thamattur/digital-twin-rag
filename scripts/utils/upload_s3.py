#!/usr/bin/env python3
"""
S3 Upload Script for LocalStack
Works around AWS CLI compatibility issues
"""

import boto3
import sys
import os
from pathlib import Path

# Configuration
LOCALSTACK_URL = "http://localhost:4566"
BUCKET_NAME = "digital-twin-files"

def upload_file(file_path, tenant_id, persona_id):
    """Upload file to LocalStack S3"""
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    # Get filename
    filename = os.path.basename(file_path)
    
    # Build S3 key
    s3_key = f"{tenant_id}/{persona_id}/files/{filename}"
    
    print(f"📤 Uploading to LocalStack S3")
    print(f"   File: {file_path}")
    print(f"   Tenant: {tenant_id}")
    print(f"   Persona: {persona_id}")
    print(f"   S3 Key: {s3_key}")
    print("")
    
    try:
        # Create S3 client
        s3 = boto3.client(
            's3',
            endpoint_url=LOCALSTACK_URL,
            aws_access_key_id='test',  # LocalStack doesn't validate these
            aws_secret_access_key='test',
            region_name='us-east-1'
        )
        
        # Upload file
        with open(file_path, 'rb') as f:
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=f.read()
            )
        
        print(f"✅ Upload successful!")
        print(f"   s3://{BUCKET_NAME}/{s3_key}")
        print("")
        print("Verify:")
        print(f"   aws --endpoint-url={LOCALSTACK_URL} s3 ls s3://{BUCKET_NAME}/{tenant_id}/{persona_id}/files/")
        return True
        
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        print("")
        print("Troubleshooting:")
        print("1. Check LocalStack is running:")
        print("   docker-compose ps localstack")
        print("")
        print("2. Check bucket exists:")
        print(f"   aws --endpoint-url={LOCALSTACK_URL} s3 ls")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 upload_s3.py <file> [tenant-id] [persona-id]")
        print("")
        print("Examples:")
        print("  python3 upload_s3.py test.txt")
        print("  python3 upload_s3.py test.txt tenant-123 persona-user")
        print("  python3 upload_s3.py report.pdf tenant-acme CEO")
        sys.exit(1)
    
    file_path = sys.argv[1]
    tenant_id = sys.argv[2] if len(sys.argv) > 2 else "tenant-123"
    persona_id = sys.argv[3] if len(sys.argv) > 3 else "persona-user"
    
    success = upload_file(file_path, tenant_id, persona_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
