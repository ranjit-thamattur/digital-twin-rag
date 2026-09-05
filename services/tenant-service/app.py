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
DOCUMENTS_BUCKET = os.getenv("DOCUMENTS_BUCKET_NAME", "clonemind-docs")
MCP_URL = os.getenv("MCP_URL", "http://localhost:3000")

# Initialize AWS Clients
cognito = boto3.client("cognito-idp", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
table = dynamodb.Table(TENANT_TABLE)

# Pydantic Models
# Default personas provisioned for every new tenant
DEFAULT_ALLOWED_PERSONAS = ["ceo", "manager", "analyst", "hr_manager"]
DEFAULT_PERSONA         = "ceo"

class TenantCreate(BaseModel):
    tenant_name: str
    company_name: str
    industry: str
    admin_email: str
    admin_password: str
    plan: str = "basic"  # "basic" or "premium"
    allowed_personas: List[str] = DEFAULT_ALLOWED_PERSONAS
    default_persona: str = DEFAULT_PERSONA

class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    persona: str

class TenantUpdate(BaseModel):
    is_active: Optional[bool] = None
    industry: Optional[str] = None
    company_name: Optional[str] = None
    plan: Optional[str] = None          # "basic" or "premium"
    allowed_personas: Optional[List[str]] = None
    default_persona: Optional[str] = None

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

        # Normalise personas to lowercase for consistent Qdrant collection naming
        allowed_personas = [p.lower() for p in tenant.allowed_personas]
        default_persona  = tenant.default_persona.lower()
        if default_persona not in allowed_personas:
            allowed_personas.insert(0, default_persona)

        table.put_item(
            Item={
                "tenantId":            tenant_id,
                "tenantName":          tenant.tenant_name,
                "companyName":         tenant.company_name,
                "industry":            tenant.industry,
                "adminEmail":          tenant.admin_email,
                "isActive":            True,
                "plan":                tenant.plan,
                "allowedPersonas":     allowed_personas,   # used by RAG pipeline
                "defaultPersona":      default_persona,    # fallback when persona unknown
                "createdAt":           datetime.now().isoformat(),
                "users": [
                    {"email": tenant.admin_email, "persona": default_persona}
                ],
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
async def update_tenant(tenant_id: str, update: TenantUpdate):
    """Update tenant configuration or status"""
    try:
        update_expr = "SET "
        attr_values = {}
        expr_names  = {}

        if update.is_active is not None:
            update_expr += "isActive = :act, "
            attr_values[":act"] = update.is_active
        if update.industry is not None:
            update_expr += "industry = :ind, "
            attr_values[":ind"] = update.industry
        if update.company_name is not None:
            update_expr += "companyName = :cname, "
            attr_values[":cname"] = update.company_name
        if update.plan is not None:
            update_expr += "#pl = :plan, "
            attr_values[":plan"] = update.plan
            expr_names["#pl"] = "plan"
        if update.allowed_personas is not None:
            normalised = [p.lower() for p in update.allowed_personas]
            update_expr += "allowedPersonas = :ap, "
            attr_values[":ap"] = normalised
        if update.default_persona is not None:
            update_expr += "defaultPersona = :dp, "
            attr_values[":dp"] = update.default_persona.lower()

        if not attr_values:
            return {"success": True, "message": "No changes requested"}

        update_expr = update_expr.rstrip(", ")

        table.update_item(
            Key={"tenantId": tenant_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=attr_values,
            **(({"ExpressionAttributeNames": expr_names}) if expr_names else {})
        )
        return {"success": True, "message": "Tenant updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tenants/{tenant_id}/users")
async def add_user_to_tenant(tenant_id: str, user: UserCreate):
    """Create additional Cognito user and link to tenant.
    Validates the requested persona against the tenant's allowedPersonas.
    """
    try:
        # 0. Fetch tenant and validate persona
        tenant_resp = table.get_item(Key={"tenantId": tenant_id})
        tenant_item = tenant_resp.get("Item")
        if not tenant_item:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

        allowed_personas = tenant_item.get("allowedPersonas", [])
        default_persona  = tenant_item.get("defaultPersona", "ceo")
        persona = user.persona.lower()

        if allowed_personas and persona not in allowed_personas:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Persona '{persona}' is not allowed for tenant '{tenant_id}'. "
                    f"Allowed: {allowed_personas}. "
                    f"To add a new persona, update the tenant's allowedPersonas first."
                )
            )

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
                ":new_user":    [{"email": user.email, "persona": persona}],
                ":empty_list": []
            }
        )

        return {"success": True, "message": f"User {user.email} added to tenant as '{persona}'"}
    except HTTPException:
        raise
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
                        "tone": tenant.get("tone", "professional"),
                        "specialInstructions": tenant.get("specialInstructions", ""),
                        "plan": tenant.get("plan", "basic")  # default to basic
                    }
        
        return {"found": False, "tenantId": "default", "personaId": "user"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Document management endpoints
# ─────────────────────────────────────────────────────────────────────────────

class UploadUrlRequest(BaseModel):
    personaId: str
    fileName: str
    contentType: str = "application/octet-stream"

@app.post("/api/tenants/{tenant_id}/upload-url")
async def get_upload_url(tenant_id: str, req: UploadUrlRequest):
    """Generate a presigned S3 URL for direct browser upload."""
    try:
        persona = req.personaId.lower().strip()
        s3_key  = f"{tenant_id}/{persona}/{req.fileName}"
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket":      DOCUMENTS_BUCKET,
                "Key":         s3_key,
                "ContentType": req.contentType,
            },
            ExpiresIn=300,  # 5 minutes
        )
        return {"uploadUrl": url, "s3Key": s3_key, "bucket": DOCUMENTS_BUCKET}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tenants/{tenant_id}/documents")
async def list_documents(tenant_id: str, personaId: Optional[str] = None):
    """List documents uploaded to S3 for this tenant (optionally filtered by persona)."""
    try:
        prefix = f"{tenant_id}/"
        if personaId:
            prefix = f"{tenant_id}/{personaId.lower()}/"

        resp    = s3.list_objects_v2(Bucket=DOCUMENTS_BUCKET, Prefix=prefix)
        objects = resp.get("Contents", [])

        docs = []
        for obj in objects:
            key   = obj["Key"]
            parts = key.split("/")
            docs.append({
                "s3Key":       key,
                "personaId":   parts[1] if len(parts) > 2 else "unknown",
                "fileName":    parts[-1],
                "sizeBytes":   obj["Size"],
                "uploadedAt":  obj["LastModified"].isoformat(),
            })

        # Sort newest first
        docs.sort(key=lambda x: x["uploadedAt"], reverse=True)
        return {"documents": docs, "count": len(docs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BrainTestRequest(BaseModel):
    personaId: str
    query: str

@app.post("/api/tenants/{tenant_id}/test-brain")
async def test_brain(tenant_id: str, req: BrainTestRequest):
    """Proxy a test query to the MCP server for this tenant."""
    import httpx
    try:
        payload = {
            "query":         req.query,
            "tenantId":      tenant_id,
            "personaId":     req.personaId.lower(),
            "system_prompt": "",
            "messages":      [],
            "plan":          "basic",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{MCP_URL}/call/generate_twin_response",
                json=payload,
            )
        if resp.status_code == 200:
            data = resp.json()
            return {"success": True, "response": data.get("content", str(data))}
        else:
            return {"success": False, "response": f"MCP error {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"success": False, "response": f"Could not reach MCP server: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
