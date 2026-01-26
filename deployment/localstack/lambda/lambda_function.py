"""
Lambda Function: S3 Upload Processor
Extracts text and calls MCP Server for knowledge ingestion

S3 Structure: <tenant_id>/<persona>/<filename>
"""

import json
import boto3
import os
from urllib.parse import unquote_plus
import io

# Optional: These would need to be in a Lambda layer or packaged with the zip
# For LocalStack, we assume the environment or deployment handles these
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from docx import Document
except ImportError:
    Document = None

# Configuration
# Note: For LocalStack inside Docker, use the container name for the MCP server
s3_client = boto3.client('s3', endpoint_url=os.environ.get('AWS_S3_ENDPOINT'))
MCP_INGEST_URL = os.environ.get('MCP_SERVER_URL', 'http://mcp-server-dt:8080/call/ingest_knowledge')

def extract_text_from_pdf(file_bytes):
    if not PyPDF2: return "PDF Reader not available"
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"PDF Error: {e}"

def extract_text_from_docx(file_bytes):
    if not Document: return "DOCX Reader not available"
    try:
        doc = Document(io.BytesIO(file_bytes))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"DOCX Error: {e}"

def parse_s3_path(s3_key):
    parts = s3_key.split('/', 2)
    if len(parts) < 2:
        return {'tenant_id': 'default', 'persona': 'user', 'file_name': s3_key}
    
    return {
        'tenant_id': parts[0],
        'persona': parts[1],
        'file_name': parts[2] if len(parts) > 2 else parts[1]
    }

def lambda_handler(event, context):
    print("Event received:", json.dumps(event))
    
    try:
        # Handle S3 Event (Direct or from EventBridge)
        if 'Records' in event:
            record = event['Records'][0]
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
        else:
            detail = event.get('detail', {})
            bucket = detail.get('bucket', {}).get('name')
            key = unquote_plus(detail.get('object', {}).get('key', ''))

        print(f"Processing s3://{bucket}/{key}")
        
        path_info = parse_s3_path(key)
        
        # Download from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_bytes = response['Body'].read()
        
        # Extract content
        ext = key.lower().split('.')[-1]
        content = ""
        
        if ext == 'pdf':
            content = extract_text_from_pdf(file_bytes)
        elif ext in ['docx', 'doc']:
            content = extract_text_from_docx(file_bytes)
        elif ext == 'txt':
            content = file_bytes.decode('utf-8', errors='ignore')
        else:
            content = f"Uploaded file: {path_info['file_name']}"

        # Ingest into MCP
        payload = {
            "text": content,
            "tenantId": path_info['tenant_id'],
            "metadata": {
                "filename": path_info['file_name'],
                "personaId": path_info['persona'],
                "s3Key": key,
                "s3Bucket": bucket
            }
        }
        
        print(f"Calling MCP: {MCP_INGEST_URL}")
        
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            MCP_INGEST_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                status_code = response.getcode()
                response_text = response.read().decode('utf-8')
                
                if status_code == 200:
                    print("✅ Successfully ingested into MCP")
                    return {'statusCode': 200, 'body': 'Success'}
                else:
                    print(f"❌ MCP Error: {status_code} - {response_text}")
                    return {'statusCode': status_code, 'body': response_text}
        except urllib.error.HTTPError as e:
            error_text = e.read().decode('utf-8')
            print(f"❌ MCP HTTP Error: {e.code} - {error_text}")
            return {'statusCode': e.code, 'body': error_text}
        except Exception as e:
            print(f"❌ MCP Connection Error: {str(e)}")
            return {'statusCode': 500, 'body': str(e)}

    except Exception as e:
        print(f"Fatal Error: {e}")
        return {'statusCode': 500, 'body': str(e)}
