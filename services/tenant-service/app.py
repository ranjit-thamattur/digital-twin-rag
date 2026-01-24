from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import boto3
from datetime import datetime
import uuid

app = FastAPI(title="CloneMind Tenant Management API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS Configuration
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
TENANT_TABLE = os.getenv("TENANT_TABLE", "TenantMetadata")

# Initialize AWS Clients
cognito = boto3.client("cognito-idp", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TENANT_TABLE)

# Pydantic Models
class TenantCreate(BaseModel):
    tenant_name: str
    company_name: str
    industry: str
    tone: str = "professional"
    special_instructions: str = ""
    admin_email: str
    admin_password: str

class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    persona: str

# Helper Functions
def create_cognito_user(email: str, password: str, first_name: str, last_name: str, tenant_id: str):
    """Create user in Cognito User Pool"""
    try:
        # 1. Create User
        response = cognito.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:tenant_id", "Value": tenant_id} # Assuming custom attribute exists
            ],
            TemporaryPassword=password,
            MessageAction="SUPPRESS"
        )
        
        # 2. Set password permanently
        cognito.admin_set_user_password(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            Password=password,
            Permanent=True
        )
        return True
    except Exception as e:
        print(f"Cognito Error: {str(e)}")
        return False

# API Endpoints
@app.get("/")
async def root():
    return {"message": "CloneMind Tenant Management API", "auth": "Cognito", "db": "DynamoDB"}

@app.post("/api/tenants")
async def create_tenant(tenant: TenantCreate):
    """Create new tenant with admin user in Cognito and metadata in DynamoDB"""
    tenant_id = f"tenant-{tenant.tenant_name.lower().replace(' ', '')}"
    
    try:
        # 1. Create Admin User in Cognito
        success = create_cognito_user(
            tenant.admin_email, 
            tenant.admin_password, 
            "Admin", 
            tenant.tenant_name, 
            tenant_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create Cognito user")

        # 2. Store Tenant Metadata in DynamoDB
        table.put_item(
            Item={
                "tenantId": tenant_id,
                "tenantName": tenant.tenant_name,
                "companyName": tenant.company_name,
                "industry": tenant.industry,
                "tone": tenant.tone,
                "specialInstructions": tenant.special_instructions,
                "adminEmail": tenant.admin_email,
                "isActive": True,
                "createdAt": datetime.now().isoformat(),
                "users": [
                    {"email": tenant.admin_email, "persona": "CEO"}
                ],
                "personas": {
                    "CEO": {"focus": "strategic", "style": "executive"},
                    "manager": {"focus": "operational", "style": "actionable"},
                    "analyst": {"focus": "data", "style": "technical"}
                }
            }
        )
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "message": f"Tenant '{tenant.tenant_name}' registered successfully in Cognito",
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/user/lookup")
async def lookup_user(email: str):
    """Lookup user tenant and persona from DynamoDB"""
    try:
        # Scan or Query based on email (Ideally use a GSI on email if many users)
        # For QA, we'll scan for simplicity or assume we know the tenant
        response = table.scan() # Warning: slow for production
        items = response.get("Items", [])
        
        for tenant in items:
            for user in tenant.get("users", []):
                if user["email"] == email:
                    return {
                        "found": True,
                        "tenantId": tenant["tenantId"],
                        "personaId": user["persona"],
                        "companyName": tenant["companyName"]
                    }
        
        return {"found": False, "tenantId": "default", "personaId": "user"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
