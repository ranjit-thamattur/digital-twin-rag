from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import boto3
from datetime import datetime
import uuid

app = FastAPI(title="Peak AI 1.0 Tenant Management API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS Configuration - Use AWS_REGION if available (CDK standard), otherwise default
REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
TENANT_TABLE = os.getenv("TENANT_TABLE", "clonemind-tenants")

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

class StatusUpdate(BaseModel):
    is_active: bool

# Helper Functions
def create_cognito_user(email: str, password: str, first_name: str, last_name: str, tenant_id: str):
    """Create user in Cognito User Pool with idempotency"""
    try:
        # 1. Create User
        try:
            cognito.admin_create_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "given_name", "Value": first_name},
                    {"Name": "family_name", "Value": last_name},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "custom:tenant_id", "Value": tenant_id}
                ],
                TemporaryPassword=password,
                MessageAction="SUPPRESS"
            )
            print(f"Cognito: User {email} created.")
        except cognito.exceptions.UsernameExistsException:
            print(f"Cognito: User {email} already exists, proceeding to password/db sync.")

        # 2. Set password permanently (ensures user can login even if previous attempt was partial)
        try:
            cognito.admin_set_user_password(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=email,
                Password=password,
                Permanent=True
            )
        except Exception as pe:
            print(f"Cognito Password Warning: {str(pe)}")
            
        return True
    except Exception as e:
        print(f"CRITICAL Cognito Error: {str(e)}")
        return False

# API Endpoints
@app.get("/")
async def root():
    """Serve the Admin Portal HTML"""
    return FileResponse("admin-portal.html")

@app.get("/api/tenants")
async def list_tenants():
    """List all tenants from DynamoDB"""
    try:
        response = table.scan()
        return {"tenants": response.get("Items", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tenants")
async def create_tenant(tenant: TenantCreate):
    """Create new tenant with admin user in Cognito and metadata in DynamoDB"""
    tenant_id = f"tenant-{tenant.tenant_name.lower().replace(' ', '')}"
    print(f"Starting registration for tenant: {tenant_id}")
    
    try:
        # 1. Create Admin User in Cognito
        print(f"Step 1: Registering {tenant.admin_email} in Cognito...")
        success = create_cognito_user(
            tenant.admin_email, 
            tenant.admin_password, 
            "Admin", 
            tenant.tenant_name, 
            tenant_id
        )
        
        if not success:
            print("ERROR: Cognito registration failed.")
            raise HTTPException(status_code=500, detail="Failed to create Cognito user")

        # 2. Store Tenant Metadata in DynamoDB
        print(f"Step 2: Storing metadata for {tenant_id} in DynamoDB table '{TENANT_TABLE}'...")
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
        print("Step 3: DynamoDB write successful.")
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "message": f"Tenant '{tenant.tenant_name}' registered successfully",
        }
        
    except Exception as e:
        print(f"ERROR in create_tenant: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Fetch tenant configuration"""
    try:
        response = table.get_item(Key={"tenantId": tenant_id})
        item = response.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="Tenant not found")
        # Ensure 'users' field exists
        if "users" not in item:
            item["users"] = []
        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/tenants/{tenant_id}")
async def update_tenant_status(tenant_id: str, status: StatusUpdate):
    """Toggle tenant active status"""
    try:
        table.update_item(
            Key={"tenantId": tenant_id},
            UpdateExpression="SET isActive = :val",
            ExpressionAttributeValues={":val": status.is_active}
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tenants/{tenant_id}/users")
async def add_user_to_tenant(tenant_id: str, user: UserCreate):
    """Create additional Cognito user and link to tenant"""
    try:
        # 1. Create in Cognito
        success = create_cognito_user(
            user.email,
            user.password,
            user.first_name,
            user.last_name,
            tenant_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create Cognito user")
            
        # 2. Add to DynamoDB 'users' list
        table.update_item(
            Key={"tenantId": tenant_id},
            UpdateExpression="SET #u = list_append(if_not_exists(#u, :empty_list), :new_user)",
            ExpressionAttributeNames={"#u": "users"},
            ExpressionAttributeValues={
                ":new_user": [{"email": user.email, "persona": user.persona}],
                ":empty_list": []
            }
        )
        
        return {"success": True, "message": f"User {user.email} added to tenant"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/user/lookup")
async def lookup_user(email: str):
    """Lookup user tenant and persona for the RAG pipeline"""
    try:
        response = table.scan()
        items = response.get("Items", [])
        
        for tenant in items:
            for user in tenant.get("users", []):
                if user["email"].lower() == email.lower():
                    return {
                        "found": True,
                        "tenantId": tenant["tenantId"],
                        "personaId": user.get("persona", "user"),
                        "companyName": tenant.get("companyName", "Unknown Corp"),
                        "tone": tenant.get("tone", "professional")
                    }
        
        return {"found": False, "tenantId": "default", "personaId": "user"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
