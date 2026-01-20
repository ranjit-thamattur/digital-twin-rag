# Complete Integration: Tenant Service → OpenWebUI & N8N

## Overview

Replace hardcoded PERSONA_MAP and prompt templates with **dynamic API calls** to tenant service.

---

## Step 1: Add User Lookup Endpoint to Tenant Service

**File:** `services/tenant-service/app.py`

Add this endpoint before `if __name__ == "__main__":`:

```python
@app.get("/api/user/lookup")
async def get_user_by_email(email: str, db = Depends(get_db)):
    """Get user's tenant and persona by email"""
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
        return {
            "found": False,
            "tenantId": "default",
            "personaId": "user",
            "email": email
        }
    
    return {
        "found": True,
        "tenantId": user['tenant_id'],
        "personaId": user['persona'],
        "companyName": user['company_name'],
        "email": email
    }
```

**Restart tenant service:**
```bash
docker compose restart tenant-service
```

---

## Step 2: Test the New Endpoint

```bash
# Test with existing user
curl "http://localhost:8000/api/user/lookup?email=admin@acmecorp.com"

# Response:
{
  "found": true,
  "tenantId": "tenant-acmecorp",
  "personaId": "CEO",
  "companyName": "ACME Corporation",
  "email": "admin@acmecorp.com"
}

# Test with unknown user
curl "http://localhost:8000/api/user/lookup?email=unknown@test.com"

# Response:
{
  "found": false,
  "tenantId": "default",
  "personaId": "user",
  "email": "unknown@test.com"
}
```

---

## Step 3: Update OpenWebUI Pipeline

**File:** `workflows/openwebui/pipeline-dynamic.py`

### Replace PERSONA_MAP with API Call:

**Find this section (lines ~48-64):**
```python
# OLD - REMOVE THIS:
PERSONA_MAP = {
    "alice.tenanta@gmail.com": "CEO",
    "bob.tenanta@gmail.com": "manager",
    # ...
}
```

**Replace with:**
```python
def get_user_tenant_persona(self, email: str) -> tuple:
    """Get user's tenant and persona from tenant service API"""
    try:
        response = requests.get(
            "http://tenant-service-dt:8000/api/user/lookup",
            params={"email": email},
            timeout=2
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                print(f"[Self² AI] ✅ User: {email} → {data['tenantId']}/{data['personaId']}")
                return data["tenantId"], data["personaId"]
        
        print(f"[Self² AI] ⚠️ User {email} not found, using default")
        return "default", "user"
        
    except Exception as e:
        print(f"[Self² AI] ❌ API error: {e}")
        return "default", "user"
```

### Update get_tenant_persona() method (lines ~155-175):

**Find:**
```python
def get_tenant_persona(self, user_info: dict, __user__: dict = None) -> tuple:
    # Extract email
    email = __user__.get("email") if __user__ else user_info.get("email")
    
    # OLD WAY - using PERSONA_MAP
    persona_id = self.PERSONA_MAP.get(email, "user")
    # ...
```

**Replace with:**
```python
def get_tenant_persona(self, user_info: dict, __user__: dict = None) -> tuple:
    # Extract email
    email = __user__.get("email") if __user__ else user_info.get("email")
    
    # NEW WAY - call API
    tenant_id, persona_id = self.get_user_tenant_persona(email)
    
    print(f"[Self² AI] ✅ Final: {tenant_id} / {persona_id}")
    return tenant_id, persona_id
```

---

## Step 4: Update File Sync Service

**File:** `services/file-sync/sync_service.py`

### Replace PERSONA_MAP (lines ~16-30):

**Find:**
```python
# OLD - REMOVE:
PERSONA_MAP = {
    "alice.tenanta@gmail.com": ("tenant-tenanta", "CEO"),
    "bob.tenanta@gmail.com": ("tenant-tenanta", "manager"),
    # ...
}
```

**Replace with:**
```python
import requests

def get_user_tenant_persona(email: str) -> tuple:
    """Get from tenant service API"""
    try:
        response = requests.get(
            "http://tenant-service-dt:8000/api/user/lookup",
            params={"email": email},
            timeout=2
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data["tenantId"], data["personaId"]
        
        return "default", "user"
        
    except:
        return "default", "user"
```

### Update extract_tenant_persona() function (lines ~70-85):

**Find:**
```python
def extract_tenant_persona(email):
    # OLD:
    if email in PERSONA_MAP:
        tenant_id, persona_id = PERSONA_MAP[email]
    # ...
```

**Replace with:**
```python
def extract_tenant_persona(email):
    # NEW - call API:
    tenant_id, persona_id = get_user_tenant_persona(email)
    
    logger.info(f"User {email} → {tenant_id}/{persona_id}")
    return tenant_id, persona_id
```

---

## Step 5: Get Tenant-Specific Prompts in N8N

**Endpoint Already Exists!**

```bash
# Get prompt configuration for a tenant
curl http://localhost:8000/api/prompts/tenant-acmecorp

# Response:
{
  "tenantId": "tenant-acmecorp",
  "companyName": "ACME Corporation",
  "industry": "Manufacturing",
  "tone": "professional and technical",
  "specialInstructions": "Focus on operational efficiency...",
  "personas": {
    "CEO": {
      "focus": "strategic decisions",
      "style": "executive summary",
      "additionalContext": "Emphasize business impact"
    },
    "manager": {
      "focus": "operational metrics",
      "style": "detailed and actionable",
      "additionalContext": "Focus on execution"
    },
    "analyst": {
      "focus": "data analysis",
      "style": "technical and precise",
      "additionalContext": "Provide detailed analytics"
    }
  }
}
```

### Update N8N "Build Prompt" Node:

**Replace hardcoded prompts with API call:**

```javascript
// In N8N Build Prompt node
const tenantId = buildNode.json.tenantId;
const personaId = buildNode.json.personaId;

// Load prompt config from API
const configResponse = await this.helpers.request({
  method: 'GET',
  url: `http://tenant-service-dt:8000/api/prompts/${tenantId}`,
  json: true
});

// Build dynamic system prompt
const personaConfig = configResponse.personas[personaId] || {};
const systemPrompt = `You are an AI assistant for ${configResponse.companyName}, a ${configResponse.industry} company.

Use ${configResponse.tone} tone in your responses.

${configResponse.specialInstructions}

For ${personaId} persona: ${personaConfig.additionalContext}

IMPORTANT: Use ONLY the context provided below.`;

// Rest of prompt building...
const ragPrompt = `${systemPrompt}\n\nContext:\n${contextText}\n\nQuestion: ${query}\n\nAnswer:`;
```

---

## Step 6: Restart Services

```bash
cd /Users/ranjitt/Ranjit/digital-twin-rag/deployment/docker

# Restart all affected services
docker compose restart tenant-service
docker compose restart file-sync
docker compose restart openwebui

# Check logs
docker logs tenant-service-dt --tail 20
docker logs file-sync-dt --tail 20
docker logs openwebui --tail 20
```

---

## Step 7: Test End-to-End

### Create a test user via UI:
1. Open http://localhost:8000/admin
2. Click "➕ Add User" on your tenant
3. Add:
   - Email: `test.user@acmecorp.com`
   - Persona: `manager`
   - Password: `Test@2024`

### Test the flow:
```bash
# 1. Verify user lookup works
curl "http://localhost:8000/api/user/lookup?email=test.user@acmecorp.com"
# Should return: tenantId=tenant-acmecorp, personaId=manager

# 2. Login to OpenWebUI
open http://localhost:3000
# Login with: test.user@acmecorp.com / Test@2024

# 3. Upload a file
# Should be stored at: s3://tenant-acmecorp/manager/filename.pdf

# 4. Ask a question
# Should get manager-specific response!
```

---

## Benefits of This Approach

✅ **No More Hardcoding** - Add users via UI, they work immediately  
✅ **Centralized Management** - One source of truth (database)  
✅ **Dynamic Prompts** - Change prompts via UI, no code changes  
✅ **Scalable** - Support unlimited tenants and users  
✅ **Consistent** - Same user/persona logic across all services  

---

## API Endpoints Summary

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `GET /api/user/lookup?email=` | Get user's tenant & persona | OpenWebUI, File-Sync |
| `GET /api/prompts/{tenant_id}` | Get tenant prompt config | N8N |
| `GET /api/tenants` | List all tenants | Admin UI |
| `POST /api/tenants` | Create tenant | Admin UI |
| `POST /api/tenants/{id}/users` | Add user to tenant | Admin UI |

---

## Quick Commands

```bash
# Add user lookup endpoint
vim services/tenant-service/app.py  # Add endpoint code

# Update OpenWebUI pipeline
vim workflows/openwebui/pipeline-dynamic.py  # Replace PERSONA_MAP

# Update file-sync
vim services/file-sync/sync_service.py  # Replace PERSONA_MAP

# Restart
docker compose restart tenant-service file-sync openwebui

# Test
curl "http://localhost:8000/api/user/lookup?email=YOUR_EMAIL"
curl "http://localhost:8000/api/prompts/YOUR_TENANT_ID"
```

---

**Ready to implement!** Start with Step 1 (add API endpoint) and test each step. 🚀
