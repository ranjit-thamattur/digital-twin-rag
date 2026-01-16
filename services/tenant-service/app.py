"""
Tenant Management Service
Handles CRUD operations for tenants and tenant provisioning
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid
import os
import httpx
from sqlalchemy import create_engine, Column, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://keycloak:keycloak_password@postgres:5432/tenant_management"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class TenantDB(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    domain = Column(String(255))
    settings = Column(JSON, default={})
    subscription_plan = Column(String(50), default="free")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Pydantic models
class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    domain: Optional[str] = None
    subscription_plan: str = "free"

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    settings: Optional[dict] = None
    subscription_plan: Optional[str] = None
    status: Optional[str] = None

class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    domain: Optional[str]
    settings: dict
    subscription_plan: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# FastAPI app
app = FastAPI(
    title="Self² AI - Tenant Management",
    description="Multi-tenant SaaS tenant management API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Keycloak configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "digital-twin")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

async def provision_tenant_resources(tenant_slug: str):
    """
    Provision resources for a new tenant:
    1. Create Qdrant collection
    2. Create Keycloak group (optional)
    """
    collection_name = f"{tenant_slug}_knowledge"
    
    # Create Qdrant collection
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(
                f"{QDRANT_URL}/collections/{collection_name}",
                json={
                    "vectors": {
                        "size": 768,
                        "distance": "Cosine"
                    }
                },
                timeout=30.0
            )
            if response.status_code not in [200, 201, 409]:  # 409 = already exists
                print(f"Warning: Qdrant collection creation returned {response.status_code}")
        except Exception as e:
            print(f"Error creating Qdrant collection: {e}")
    
    # Create indexes
    indexes = ["tenantId", "personaId", "fileName", "s3Key"]
    async with httpx.AsyncClient() as client:
        for field in indexes:
            try:
                await client.put(
                    f"{QDRANT_URL}/collections/{collection_name}/index",
                    json={
                        "field_name": field,
                        "field_schema": "keyword"
                    },
                    timeout=30.0
                )
            except Exception as e:
                print(f"Error creating index {field}: {e}")

# Routes
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "tenant-service"}

@app.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant and provision resources"""
    
    # Check if slug already exists
    existing = db.query(TenantDB).filter(TenantDB.slug == tenant.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")
    
    # Create tenant
    db_tenant = TenantDB(
        name=tenant.name,
        slug=tenant.slug,
        domain=tenant.domain,
        subscription_plan=tenant.subscription_plan
    )
    
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    
    # Provision resources asynchronously
    try:
        await provision_tenant_resources(tenant.slug)
    except Exception as e:
        print(f"Error provisioning resources: {e}")
        # Don't fail the request if provisioning fails
    
    return db_tenant

@app.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all tenants"""
    query = db.query(TenantDB)
    
    if status:
        query = query.filter(TenantDB.status == status)
    
    tenants = query.offset(skip).limit(limit).all()
    return tenants

@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get tenant by ID"""
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@app.get("/tenants/slug/{slug}", response_model=TenantResponse)
async def get_tenant_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get tenant by slug"""
    tenant = db.query(TenantDB).filter(TenantDB.slug == slug).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@app.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    tenant_update: TenantUpdate,
    db: Session = Depends(get_db)
):
    """Update tenant"""
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    update_data = tenant_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)
    
    tenant.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tenant)
    
    return tenant

@app.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete (deactivate) tenant"""
    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Soft delete - set status to inactive
    tenant.status = "inactive"
    tenant.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Tenant deactivated successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
