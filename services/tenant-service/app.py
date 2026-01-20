from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import requests
from datetime import datetime

app = FastAPI(title="Digital Twin Tenant Management API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://keycloak:keycloak_password@postgres:5432/postgres")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

# Keycloak configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USER", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "self2ai")

# Pydantic Models
class TenantCreate(BaseModel):
    tenant_name: str
    company_name: str
    industry: str
    tone: str = "professional"
    special_instructions: str = ""
    admin_email: str
    admin_password: str

class TenantUpdate(BaseModel):
    company_name: Optional[str] = None
    industry: Optional[str] = None
    tone: Optional[str] = None
    special_instructions: Optional[str] = None
    is_active: Optional[bool] = None

class PersonaCreate(BaseModel):
    persona_name: str
    focus: str
    style: str
    additional_context: str = ""

class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    persona: str

# Keycloak Helper Functions
def get_keycloak_token():
    """Get Keycloak admin token"""
    response = requests.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "username": KEYCLOAK_ADMIN_USER,
            "password": KEYCLOAK_ADMIN_PASSWORD,
            "grant_type": "password",
            "client_id": "admin-cli"
        }
    )
    return response.json()["access_token"]

def create_keycloak_user(tenant_id: str, email: str, password: str, first_name: str, last_name: str):
    """Create user in Keycloak"""
    token = get_keycloak_token()
    
    # Create user
    user_data = {
        "username": email.split('@')[0] + f".{tenant_id}",
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
        "emailVerified": True,
        "credentials": [{
            "type": "password",
            "value": password,
            "temporary": False
        }]
    }
    
    response = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=user_data
    )
    
    return response.status_code == 201

# Database initialization
@app.on_event("startup")
async def startup():
    """Initialize database tables"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Tenants table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(100) UNIQUE NOT NULL,
            tenant_name VARCHAR(255) NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            industry VARCHAR(100),
            tone VARCHAR(100) DEFAULT 'professional',
            special_instructions TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Personas table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personas (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
            persona_name VARCHAR(50) NOT NULL,
            focus TEXT,
            style VARCHAR(100),
            additional_context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, persona_name)
        )
    """)
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_users (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
            email VARCHAR(255) UNIQUE NOT NULL,
            persona VARCHAR(50),
            keycloak_user_id VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Prompt templates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
            template_type VARCHAR(50) DEFAULT 'system',
            template_content TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

# API Endpoints

@app.get("/")
async def root():
    return {"message": "Digital Twin Tenant Management API", "version": "1.0"}

@app.get("/admin")
async def admin_portal():
    """Serve admin portal HTML"""
    return FileResponse("/app/admin-portal.html")

# Tenants
@app.post("/api/tenants")
async def create_tenant(tenant: TenantCreate, db = Depends(get_db)):
    """Create new tenant with admin user in Keycloak"""
    cursor = db.cursor()
    
    # Generate tenant_id
    tenant_id = f"tenant-{tenant.tenant_name.lower().replace(' ', '')}"
    
    try:
        # Insert tenant
        cursor.execute("""
            INSERT INTO tenants (tenant_id, tenant_name, company_name, industry, tone, special_instructions)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (tenant_id, tenant.tenant_name, tenant.company_name, tenant.industry, tenant.tone, tenant.special_instructions))
        
        tenant_db_id = cursor.fetchone()['id']
        
        # Create admin user in Keycloak
        keycloak_success = create_keycloak_user(
            tenant_id,
            tenant.admin_email,
            tenant.admin_password,
            "Admin",
            tenant.tenant_name
        )
        
        if not keycloak_success:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create Keycloak user")
        
        # Add admin user to database
        cursor.execute("""
            INSERT INTO tenant_users (tenant_id, email, persona)
            VALUES (%s, %s, %s)
        """, (tenant_id, tenant.admin_email, "CEO"))
        
        # Create default personas
        default_personas = [
            ("CEO", "strategic decisions", "executive summary", "Emphasize business impact"),
            ("manager", "operational metrics", "detailed and actionable", "Focus on execution"),
            ("analyst", "data analysis", "technical and precise", "Provide detailed analytics")
        ]
        
        for persona_name, focus, style, context in default_personas:
            cursor.execute("""
                INSERT INTO personas (tenant_id, persona_name, focus, style, additional_context)
                VALUES (%s, %s, %s, %s, %s)
            """, (tenant_id, persona_name, focus, style, context))
        
        db.commit()
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "message": f"Tenant '{tenant.tenant_name}' created successfully",
            "admin_user": tenant.admin_email,
            "login_url": "http://localhost:3000"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()

@app.get("/api/tenants")
async def list_tenants(db = Depends(get_db)):
    """List all tenants"""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC")
    tenants = cursor.fetchall()
    cursor.close()
    return {"tenants": tenants}

@app.get("/api/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, db = Depends(get_db)):
    """Get tenant details with personas and users"""
    cursor = db.cursor()
    
    # Get tenant
    cursor.execute("SELECT * FROM tenants WHERE tenant_id = %s", (tenant_id,))
    tenant = cursor.fetchone()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get personas
    cursor.execute("SELECT * FROM personas WHERE tenant_id = %s", (tenant_id,))
    personas = cursor.fetchall()
    
    # Get users
    cursor.execute("SELECT email, persona, is_active, created_at FROM tenant_users WHERE tenant_id = %s", (tenant_id,))
    users = cursor.fetchall()
    
    cursor.close()
    
    return {
        "tenant": tenant,
        "personas": personas,
        "users": users
    }

@app.put("/api/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, tenant: TenantUpdate, db = Depends(get_db)):
    """Update tenant configuration"""
    cursor = db.cursor()
    
    updates = []
    params = []
    
    if tenant.company_name:
        updates.append("company_name = %s")
        params.append(tenant.company_name)
    if tenant.industry:
        updates.append("industry = %s")
        params.append(tenant.industry)
    if tenant.tone:
        updates.append("tone = %s")
        params.append(tenant.tone)
    if tenant.special_instructions is not None:
        updates.append("special_instructions = %s")
        params.append(tenant.special_instructions)
    if tenant.is_active is not None:
        updates.append("is_active = %s")
        params.append(tenant.is_active)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(tenant_id)
    
    query = f"UPDATE tenants SET {', '.join(updates)} WHERE tenant_id = %s"
    cursor.execute(query, params)
    db.commit()
    cursor.close()
    
    return {"success": True, "message": "Tenant updated"}

@app.delete("/api/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, db = Depends(get_db)):
    """Soft delete tenant (set inactive)"""
    cursor = db.cursor()
    cursor.execute("UPDATE tenants SET is_active = FALSE WHERE tenant_id = %s", (tenant_id,))
    db.commit()
    cursor.close()
    return {"success": True, "message": "Tenant deactivated"}

# Users
@app.post("/api/tenants/{tenant_id}/users")
async def create_user(tenant_id: str, user: UserCreate, db = Depends(get_db)):
    """Create user for tenant"""
    cursor = db.cursor()
    
    try:
        # Create in Keycloak
        keycloak_success = create_keycloak_user(
            tenant_id,
            user.email,
            user.password,
            user.first_name,
            user.last_name
        )
        
        if not keycloak_success:
            raise HTTPException(status_code=500, detail="Failed to create Keycloak user")
        
        # Add to database
        cursor.execute("""
            INSERT INTO tenant_users (tenant_id, email, persona)
            VALUES (%s, %s, %s)
        """, (tenant_id, user.email, user.persona))
        
        db.commit()
        
        return {"success": True, "email": user.email}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()

# Prompt Configuration
@app.get("/api/prompts/{tenant_id}")
async def get_tenant_prompt_config(tenant_id: str, db = Depends(get_db)):
    """Get prompt configuration for N8N workflow"""
    cursor = db.cursor()
    
    # Get tenant config
    cursor.execute("SELECT * FROM tenants WHERE tenant_id = %s AND is_active = TRUE", (tenant_id,))
    tenant = cursor.fetchone()
    
    if not tenant:
        cursor.close()
        return {"error": "Tenant not found or inactive"}
    
    # Get personas
    cursor.execute("SELECT * FROM personas WHERE tenant_id = %s", (tenant_id,))
    personas = cursor.fetchall()
    
    cursor.close()
    
    # Build config for N8N
    return {
        "tenantId": tenant_id,
        "companyName": tenant['company_name'],
        "industry": tenant['industry'],
        "tone": tenant['tone'],
        "specialInstructions": tenant['special_instructions'],
        "personas": {p['persona_name']: {
            "focus": p['focus'],
            "style": p['style'],
            "additionalContext": p['additional_context']
        } for p in personas}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/api/user/lookup")
async def get_user_by_email(email: str, db = Depends(get_db)):
    """Get user's tenant and persona by email - for OpenWebUI and file-sync"""
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT tu.tenant_id, tu.persona, t.company_name
        FROM tenant_users tu
        JOIN tenants t ON tu.tenant_id = t.tenant_id
        WHERE tu.email = %s AND tu.is_active = TRUE AND t.is_active = TRUE
    """, (email,))
    
    user = cursor.fetchone()
    cursor.close()
    
    if not user:
        return {"found": False, "tenantId": "default", "personaId": "user", "email": email}
    
    return {
        "found": True,
        "tenantId": user['tenant_id'],
        "personaId": user['persona'],
        "companyName": user['company_name'],
        "email": email
    }
