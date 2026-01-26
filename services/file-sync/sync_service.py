#!/usr/bin/env python3
import os
import time
import sqlite3
import boto3
import json
import requests
from pathlib import Path

# Configuration from Environment
OPENWEBUI_DB = os.getenv("OPENWEBUI_DB", "/app/backend/data/webui.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/backend/data/uploads")
S3_BUCKET = os.getenv("S3_BUCKET")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
CHECK_INTERVAL = 10 
PROCESSED_FILE = "/app/backend/data/synced_files.json"
TENANT_SERVICE_URL = os.getenv("TENANT_SERVICE_URL", "http://tenant-service-dt:8000")

# Initialize S3 client
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
s3_params = {'region_name': REGION}
if S3_ENDPOINT:
    s3_params['endpoint_url'] = S3_ENDPOINT

s3_client = boto3.client('s3', **s3_params)

def load_processed_files():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r') as f:
                return set(json.load(f))
        except: pass
    return set()

def save_processed_file(file_id):
    processed = load_processed_files()
    processed.add(file_id)
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(list(processed), f)

def get_user_context(email):
    """Call Tenant Service to get the true tenantId and personaId for this user"""
    try:
        response = requests.get(f"{TENANT_SERVICE_URL}/api/user/lookup", params={"email": email}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data["tenantId"], data.get("personaId", "user")
    except Exception as e:
        print(f"Tenant Lookup Error: {e}")
    return "default_tenant", "user"

def sync_to_s3():
    if not os.path.exists(OPENWEBUI_DB):
        return

    processed = load_processed_files()
    
    try:
        conn = sqlite3.connect(OPENWEBUI_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # OpenWebUI 'file' table stores uploads
        cursor.execute("SELECT id, user_id, filename, path FROM file")
        files = cursor.fetchall()
        
        for f in files:
            if f['id'] in processed:
                continue
                
            # 1. Get User Email
            cursor.execute("SELECT email FROM user WHERE id = ?", (f['user_id'],))
            user = cursor.fetchone()
            email = user['email'] if user else "unknown"
            
            # 2. Get Tenant & Persona Context
            tenant_id, persona_id = get_user_context(email)
            
            # 3. Upload to S3 (Path: tenantId/personaId/filename)
            source_path = f['path']
            if not os.path.exists(source_path):
                continue
                
            s3_key = f"{tenant_id}/{persona_id}/{f['filename']}"
            print(f"Syncing {f['filename']} to s3://{S3_BUCKET}/{s3_key}")
            
            s3_client.upload_file(
                source_path, 
                S3_BUCKET, 
                s3_key,
                ExtraArgs={
                    'Metadata': {
                        'tenantId': tenant_id,
                        'personaId': persona_id
                    }
                }
            )
            
            # 4. Mark as processed
            save_processed_file(f['id'])
            processed.add(f['id'])
            
        conn.close()
    except Exception as e:
        print(f"Sync Error: {e}")

if __name__ == "__main__":
    print(f"Starting File Sync for bucket: {S3_BUCKET}")
    while True:
        sync_to_s3()
        time.sleep(CHECK_INTERVAL)
