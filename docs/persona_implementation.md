# Adding Persona Support via Keycloak

## Current State

**Issue:** Everyone gets `personaId: "user"` regardless of their actual role
**Goal:** Support multiple personas (CEO, manager, user, analyst, etc.)

## Solution: Keycloak Custom Attributes

### Option 1: User Attributes (Recommended)

Store persona as a custom user attribute in Keycloak.

#### Step 1: Add Persona to Keycloak Users

**Via Keycloak Admin UI:**

1. Login to Keycloak: `http://localhost:8080/admin`
2. Select realm: `self2ai`
3. Go to **Users** → Select user (e.g., `diana.tenantb@gmail.com`)
4. Go to **Attributes** tab
5. Add attribute:
   - **Key:** `persona`
   - **Value:** `CEO` (or `manager`, `analyst`, etc.)
6. Click **Add** → **Save**

**Repeat for all users:**
```
alice.tenanta@gmail.com → persona: CEO
diana.tenantb@gmail.com → persona: manager
bob.tenantb@gmail.com   → persona: user
```

#### Step 2: Configure OIDC to Include Persona

1. Go to **Clients** → `openwebui`
2. Go to **Client Scopes** → `openwebui-dedicated`
3. Click **Add mapper** → **Create**
4. Configure:
   ```
   Name: persona-mapper
   Mapper Type: User Attribute
   User Attribute: persona
   Token Claim Name: persona
   Claim JSON Type: String
   Add to ID token: ON
   Add to access token: ON
   Add to userinfo: ON
   ```
5. **Save**

#### Step 3: Update Pipeline to Extract Persona

**Edit:** `/Users/ranjitt/Ranjit/digital-twin-rag/workflows/openwebui/pipeline-dynamic.py`

```python
def get_tenant_persona(self, user_info: dict, __user__: dict = None) -> tuple:
    """Extract tenant and persona from user info"""
    
    # ... existing email extraction code ...
    
    # Extract persona
    persona_id = "user"  # Default
    
    # Try to get from __user__ attributes (Keycloak)
    if __user__:
        # Check custom attributes
        persona_id = __user__.get("persona", "user")
        if persona_id:
            print(f"[Self² AI] ✓ Found persona in user attributes: {persona_id}")
    
    # Fallback to role if no persona attribute
    if persona_id == "user":
        role = user_info.get("role") or __user__.get("role", "user") if __user__ else "user"
        persona_id = role
    
    print(f"[Self² AI] ✅ Final Assignment: {tenant_id} / {persona_id}")
    return tenant_id, persona_id
```

### Option 2: Map from Keycloak Roles

Use existing Keycloak roles as persona.

#### In Keycloak:

1. **Realm Roles** → Create roles:
   - `CEO`
   - `manager`
   - `analyst`
   - `user`

2. **Users** → Assign roles:
   - `alice.tenanta@gmail.com` → Role: CEO
   - `diana.tenantb@gmail.com` → Role: manager

3. **Client** → **Mappers** → Add role mapper:
   ```
   Name: roles-mapper
   Mapper Type: User Realm Role
   Token Claim Name: roles
   Add to userinfo: ON
   ```

#### In Pipeline:

```python
def get_tenant_persona(self, user_info: dict, __user__: dict = None) -> tuple:
    # ... tenant extraction ...
    
    # Get persona from roles
    persona_id = "user"  # Default
    
    if __user__:
        roles = __user__.get("roles", [])
        # Priority: CEO > manager > analyst > user
        if "CEO" in roles:
            persona_id = "CEO"
        elif "manager" in roles:
            persona_id = "manager"
        elif "analyst" in roles:
            persona_id = "analyst"
    
    return tenant_id, persona_id
```

## Testing Persona Support

### Create Test Users with Different Personas

```bash
# CEO user
curl -X POST http://localhost:8080/admin/realms/self2ai/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "username": "alice.tenanta@gmail.com",
    "email": "alice.tenanta@gmail.com",
    "enabled": true,
    "attributes": {
      "persona": ["CEO"]
    }
  }'

# Manager user  
curl -X POST http://localhost:8080/admin/realms/self2ai/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "username": "diana.tenantb@gmail.com",
    "email": "diana.tenantb@gmail.com",
    "enabled": true,
    "attributes": {
      "persona": ["manager"]
    }
  }'
```

### Upload Files with Persona

1. **Login as CEO:** `alice.tenanta@gmail.com`
2. Upload file: `executive-summary.pdf`
3. **Expected S3 path:** `tenant-tenanta/CEO/executive-summary.pdf` ✅

4. **Login as Manager:** `diana.tenantb@gmail.com`
5. Upload file: `quarterly-report.pdf`
6. **Expected S3 path:** `tenant-tenantb/manager/quarterly-report.pdf` ✅

### Verify Persona Isolation

**Qdrant should filter by BOTH tenant AND persona:**

```javascript
// N8N Search filter
filter.must.push({ 
  key: 'tenantId', 
  match: { value: 'tenant-tenanta' } 
});
filter.must.push({ 
  key: 'personaId', 
  match: { value: 'CEO' }
});
```

**Result:** CEO only sees CEO documents, manager only sees manager documents

## Implementation Steps

### 1. Update File-Sync Service

**File:** `services/file-sync/sync_service.py`

Currently uses hardcoded `persona_id = "user"`. Update to extract from Keycloak:

```python
def extract_tenant_persona(email):
    """Extract tenant and persona from email"""
    # Import OpenWebUI user data
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM user WHERE email = ?
    ''', (email,))
    user_id = cursor.fetchone()
    
    if user_id:
        # Get persona from user's OAuth data
        # (stored when they login via Keycloak)
        cursor.execute('''
            SELECT oauth_sub FROM auth WHERE user_id = ?
        ''', (user_id[0],))
        # Parse JWT to get persona claim
        # ... decode JWT and extract persona ...
    
    # For now, use default
    tenant_id = get_tenant_from_email(email)
    persona_id = "user"  # TODO: Extract from Keycloak
    
    return tenant_id, persona_id
```

**Better approach:** File-sync defaults to "user", rely on N8N to update persona later.

### 2. Check Logs for Persona

```bash
# After uploading a file
docker logs openwebui | grep "persona"

# Should see:
# [Self² AI] ✓ Found persona in user attributes: CEO
# [Self² AI] ✅ Final Assignment: tenant-tenanta / CEO
```

### 3. Verify in S3

```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://digital-twin-docs/ --recursive

# Expected structure:
# tenant-tenanta/CEO/file.pdf
# tenant-tenanta/manager/file.pdf
# tenant-tenantb/manager/file.pdf
```

## Quick Test Script

```bash
#!/bin/bash
# Test persona support

echo "=== Testing Persona Support ==="

# 1. Check current user's persona
echo "Checking alice.tenanta@gmail.com persona..."
docker exec openwebui python3 << 'PYTHON'
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.execute("SELECT email, role FROM user WHERE email LIKE '%tenanta%'")
print(cur.fetchone())
PYTHON

# 2. Upload test file as alice.tenanta@gmail.com
echo "Upload a file via UI, then check S3..."

# 3. Verify S3 path
aws --endpoint-url=http://localhost:4566 s3 ls \
  s3://digital-twin-docs/tenant-tenanta/ --recursive

echo "✅ If you see CEO/ or manager/ folders, persona is working!"
```

## Fallback Strategy

If Keycloak attribute doesn't work initially:

### Temporary: Email-based Persona Mapping

```python
PERSONA_MAP = {
    "alice.tenanta@gmail.com": "CEO",
    "diana.tenantb@gmail.com": "manager",
    "bob@anywhere.com": "user"
}

def get_tenant_persona(self, user_info: dict, __user__: dict = None):
    email = __user__.get("email", "") if __user__ else ""
    
    # Check map first
    if email in PERSONA_MAP:
        persona_id = PERSONA_MAP[email]
        print(f"[Self² AI] ✓ Mapped persona: {persona_id}")
    else:
        persona_id = "user"
    
    return tenant_id, persona_id
```

## Summary

**Current:** `personaId = "user"` (everyone)  
**Goal:** `personaId = {CEO, manager, analyst, user}` (role-based)

**Two Options:**
1. ✅ **Custom Attributes** (flexible, recommended)
2. ✅ **Keycloak Roles** (reuse existing roles)

**Choose Custom Attributes** if you want persona separate from permissions.  
**Choose Roles** if persona = Keycloak role.

Next step: Set persona attribute in Keycloak for test users!
