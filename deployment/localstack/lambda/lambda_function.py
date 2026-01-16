"""
Lambda Function: S3 Upload Processor with S3 Path Preservation
Extracts text and calls n8n with full S3 metadata

S3 Structure: <tenant_id>/<persona>/<...files>
Example: tenant-123/persona-user/documents/reports/Q4-2024.pdf
"""

import json
import boto3
import os
import requests
from urllib.parse import unquote_plus
import PyPDF2
import io
from docx import Document

# For LocalStack
s3_client = boto3.client('s3', endpoint_url=os.environ.get('AWS_ENDPOINT_URL'))
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', 'http://n8n-dt:5678/webhook/upload-document')

def extract_text_from_pdf(file_bytes):
    """Extract text from PDF"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return None

def extract_text_from_docx(file_bytes):
    """Extract text from DOCX"""
    try:
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return None

def extract_text_from_txt(file_bytes):
    """Extract text from TXT"""
    try:
        return file_bytes.decode('utf-8')
    except Exception as e:
        print(f"TXT extraction error: {e}")
        return None

def parse_s3_path(s3_key):
    """
    Parse S3 path: <tenant_id>/<persona>/<...files>
    
    Examples:
      tenant-123/persona-user/file.pdf
        → tenant: tenant-123, persona: persona-user, path: file.pdf
      
      tenant-123/persona-admin/documents/reports/Q4.pdf
        → tenant: tenant-123, persona: persona-admin, path: documents/reports/Q4.pdf
    """
    parts = s3_key.split('/', 2)  # Split into max 3 parts
    
    if len(parts) < 2:
        # Invalid structure
        return {
            'tenant_id': 'unknown',
            'persona': 'unknown',
            'file_path': s3_key,
            'file_name': s3_key.split('/')[-1],
            'is_valid': False
        }
    
    tenant_id = parts[0]
    persona = parts[1]
    file_path = parts[2] if len(parts) > 2 else ''
    file_name = file_path.split('/')[-1] if file_path else 'unknown.txt'
    
    return {
        'tenant_id': tenant_id,
        'persona': persona,
        'file_path': file_path,
        'file_name': file_name,
        's3_key': s3_key,
        'is_valid': True
    }

def lambda_handler(event, context):
    """
    Process S3 upload event and trigger n8n workflow
    """
    print("Event received:", json.dumps(event))
    
    try:
        # Extract S3 event details
        detail = event.get('detail', {})
        bucket = detail['bucket']['name']
        key = unquote_plus(detail['object']['key'])
        size = detail['object']['size']
        
        print(f"Processing: s3://{bucket}/{key} ({size} bytes)")
        
        # Parse S3 path structure
        path_info = parse_s3_path(key)
        
        if not path_info['is_valid']:
            print(f"⚠️ Invalid S3 path structure: {key}")
            print(f"   Expected: <tenant_id>/<persona>/<...files>")
        
        print(f"Tenant: {path_info['tenant_id']}")
        print(f"Persona: {path_info['persona']}")
        print(f"File Path: {path_info['file_path']}")
        print(f"File Name: {path_info['file_name']}")
        
        # Download file from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_bytes = response['Body'].read()
        
        # Extract text based on file type
        file_ext = path_info['file_name'].lower().split('.')[-1]
        
        if file_ext == 'pdf':
            content = extract_text_from_pdf(file_bytes)
        elif file_ext in ['docx', 'doc']:
            content = extract_text_from_docx(file_bytes)
        elif file_ext == 'txt':
            content = extract_text_from_txt(file_bytes)
        else:
            print(f"Unsupported file type: {file_ext}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unsupported file type: {file_ext}'})
            }
        
        if not content:
            print("Failed to extract text from file")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Text extraction failed'})
            }
        
        print(f"Extracted {len(content)} characters")
        
        # Prepare payload for n8n with full S3 metadata
        payload = {
            'fileName': path_info['file_name'],
            'content': content,
            'metadata': {
                'tenantId': path_info['tenant_id'],
                'personaId': path_info['persona'],
                's3Key': key,
                's3Bucket': bucket,
                'filePath': path_info['file_path'],
                'fileSize': size,
                'uploadDate': detail['object'].get('last-modified', ''),
                'isValidPath': path_info['is_valid']
            }
        }
        
        # Call n8n webhook
        print(f"Calling n8n webhook: {N8N_WEBHOOK_URL}")
        n8n_response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=300
        )
        
        n8n_response.raise_for_status()
        n8n_result = n8n_response.json()
        
        print(f"n8n response: {n8n_result}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'File processed successfully',
                'tenant': path_info['tenant_id'],
                'persona': path_info['persona'],
                'fileName': path_info['file_name'],
                'filePath': path_info['file_path'],
                'n8nResult': n8n_result
            })
        }
        
    except Exception as e:
        print(f"Error processing event: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'type': type(e).__name__
            })
        }
