#!/usr/bin/env python3
"""
OpenWebUI to S3 File Sync Service
Monitors OpenWebUI uploads and syncs to S3 with tenant/persona structure
"""

import os
import time
import json
import sqlite3
import boto3
from pathlib import Path
from datetime import datetime

# Configuration
OPENWEBUI_DB = "/app/backend/data/webui.db"
UPLOAD_DIR = "/app/backend/data/uploads"
S3_BUCKET = "digital-twin-docs"
S3_ENDPOINT = "http://localstack:4566"
CHECK_INTERVAL = 5  # seconds
PROCESSED_FILE = "/app/backend/data/synced_files.json"

# Initialize S3 client
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id='test',
    aws_secret_access_key='test',
    region_name='us-east-1'
)

def load_processed_files():
    """Load list of already processed file IDs"""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_processed_file(file_id):
    """Mark file as processed"""
    processed = load_processed_files()
    processed.add(file_id)
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(list(processed), f)

def get_user_email(user_id, db_conn):
    """Get user email from database"""
    cursor = db_conn.cursor()
    cursor.execute('SELECT email FROM user WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_tenant_from_email(email):
    """Extract tenant ID from email address"""
    if not email or '@' not in email:
        return 'default-tenant'
    
    # Extract from username part: alice.tenanta@gmail.com -> tenant-tenanta
    username = email.split('@')[0]
    if '.' in username:
        # Pattern: firstname.TENANT@domain -> use TENANT part
        tenant_part = username.split('.')[-1]
        return f'tenant-{tenant_part}'
    else:
        # Fallback to domain if no dot in username
        domain = email.split('@')[1].replace('.', '-')
        return f'tenant-{domain}'

def extract_tenant_persona(email):
    """Extract tenant and persona from email"""
    # Persona mapping
    PERSONA_MAP = {
        # Tenant A users
        "alice.tenanta@gmail.com": "CEO",
        "bob.tenanta@gmail.com": "manager",
        "sarah.tenanta@gmail.com": "analyst",
        
        # Tenant B users
        "diana.tenantb@gmail.com": "CEO",
        "john.tenantb@gmail.com": "manager",
        
        # Add more users here as needed
        # "user@domain.com": "persona",
    }
    
    if not email or '@' not in email:
        return 'default-tenant', 'user'
    
    # Extract tenant using the new function
    tenant_id = get_tenant_from_email(email)
    
    # Get persona from map
    persona_id = PERSONA_MAP.get(email, "user")
    
    return tenant_id, persona_id

def sync_file_to_s3(file_record, db_conn):
    """Sync a single file to S3 and trigger N8N processing"""
    file_id = file_record['id']
    user_id = file_record['user_id']
    filename = file_record['filename']
    file_path = file_record['path']
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"[Sync] File not found: {file_path}")
        return False
    
    # Get user email
    email = get_user_email(user_id, db_conn)
    if not email:
        print(f"[Sync] User email not found for user_id: {user_id}")
        return False
    
    # Extract tenant and persona
    tenant_id, persona_id = extract_tenant_persona(email)
    
    # Generate S3 key
    s3_key = f"{tenant_id}/{persona_id}/{filename}"
    
    print(f"[Sync] Uploading: {filename} → s3://{S3_BUCKET}/{s3_key}")
    
    try:
        # Read file
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_content,
            Metadata={
                'tenantId': tenant_id,
                'personaId': persona_id,
                'uploadedBy': email,
                'fileId': file_id
            }
        )
        
        print(f"[Sync] ✅ Uploaded: {s3_key}")
        
        # Trigger N8N workflow
        try:
            import requests
            
            # Decode content as text for N8N
            try:
                content_str = file_content.decode('utf-8', errors='ignore')
            except:
                content_str = str(file_content)
            
            n8n_payload = {
                'fileName': filename,
                'content': content_str,
                'metadata': {
                    'tenantId': tenant_id,
                    'personaId': persona_id,
                    's3Key': s3_key,
                    's3Bucket': S3_BUCKET
                }
            }
            
            response = requests.post(
                'http://n8n-dt:5678/webhook/upload-document',
                json=n8n_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                print(f"[Sync] ✅ N8N triggered for: {filename}")
            else:
                print(f"[Sync] ⚠️ N8N responded with: {response.status_code}")
                
        except Exception as e:
            print(f"[Sync] ⚠️ N8N trigger failed: {str(e)}")
            # Don't fail the S3 upload if N8N fails
        
        return True
        
    except Exception as e:
        print(f"[Sync] ❌ Error uploading {filename}: {str(e)}")
        return False

def watch_uploads():
    """Main watch loop"""
    print("[Sync] Starting OpenWebUI → S3 File Sync Service")
    print(f"[Sync] Monitoring: {UPLOAD_DIR}")
    print(f"[Sync] S3 Bucket: {S3_BUCKET}")
    print(f"[Sync] Check interval: {CHECK_INTERVAL}s")
    
    processed_files = load_processed_files()
    
    while True:
        try:
            # Connect to database
            conn = sqlite3.connect(OPENWEBUI_DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all uploaded files
            cursor.execute('''
                SELECT id, user_id, filename, path, created_at
                FROM file
                ORDER BY created_at DESC
            ''')
            
            files = cursor.fetchall()
            
            for file_record in files:
                file_id = file_record['id']
                
                # Skip if already processed
                if file_id in processed_files:
                    continue
                
                # Sync to S3
                if sync_file_to_s3(dict(file_record), conn):
                    save_processed_file(file_id)
                    processed_files.add(file_id)
            
            conn.close()
            
        except Exception as e:
            print(f"[Sync] Error in main loop: {str(e)}")
        
        # Wait before next check
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    watch_uploads()
