# Getting Persona from Keycloak to OpenWebUI - All Options

## Current Situation

✅ **Tenant isolation working:** `diana.tenantb` → `tenant-tenantb`  
❌ **Persona not working:** Always `"user"` instead of "CEO", "manager", etc.

**Root cause:** OpenWebUI's `__user__` parameter only has `{id, email, role}` - NO Keycloak data.

## Option 1: Email-Based Mapping (Simplest)

### How it works
Hardcode persona assignments in pipeline code:

```python
PERSONA_MAP = {
    "alice.tenanta@gmail.com": "CEO",
    "bob.tenanta@gmail.com": "manager",  
    "diana.tenantb@gmail.com": "CEO",
    "john.tenantb@gmail.com": "manager",
}
```

### Pros
✅ Works immediately  
✅ No Keycloak changes needed  
✅ Simple to understand  
✅ Fast (dictionary lookup)

### Cons
❌ Must update pipeline code for each user  
❌ Not scalable for many users  
❌ Requires pipeline reload for changes

### Best for
- Small teams (<20 users)
- Infrequent changes
- Quick testing

---

## Option 2: Parse JWT Token (Advanced)

### How it works
OpenWebUI receives JWT from Keycloak. Parse it in the pipeline to extract claims.

```python
import jwt
import base64

def get_persona_from_jwt(self, body: dict, __user__: dict):
    # Try to get JWT from metadata
    metadata = body.get("metadata", {})
    
    # JWT might be in:
    # 1. metadata.access_token
    # 2. metadata.id_token
    # 3. Need to inspect OpenWebUI's request
    
    token = metadata.get("access_token") or metadata.get("id_token")
    
    if token:
        # Decode JWT (no verification for now, just parse)
        payload = jwt.decode(token, options={"verify_signature": False})
        persona = payload.get("persona", "user")
        return persona
    
    return "user"
```

### Pros
✅ Gets data directly from Keycloak  
✅ No hardcoding needed  
✅ Automatic updates when Keycloak changes

### Cons
❌ Need to verify JWT is accessible in pipeline  
❌ Requires JWT library  
❌ More complex

### Implementation
1. Check if JWT is in `body["metadata"]`
2. Decode JWT claims
3. Extract persona from claims
4. Use in pipeline

**Need to verify:** Does OpenWebUI pass JWT to pipeline?

---

## Option 3: Call Keycloak UserInfo API (Most Reliable)

### How it works
Make HTTP call to Keycloak's userinfo endpoint with user's email:

```python
import requests

def get_persona_from_keycloak(self, email: str):
    # Get admin token
    token_url = "http://keycloak:8080/realms/self2ai/protocol/openid-connect/token"
    token_data = {
        "client_id": "admin-cli",
        "username": "admin",
        "password": "admin",
        "grant_type": "password"
    }
    
    token_response = requests.post(token_url, data=token_data)
    access_token = token_response.json()["access_token"]
    
    # Get user info
    user_url = f"http://keycloak:8080/admin/realms/self2ai/users?email={email}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    user_response = requests.get(user_url, headers=headers)
    users = user_response.json()
    
    if users:
        user_id = users[0]["id"]
        # Get attributes
        attr_url = f"http://keycloak:8080/admin/realms/self2ai/users/{user_id}"
        attr = requests.get(attr_url, headers=headers).json()
        persona = attr.get("attributes", {}).get("persona", ["user"])[0]
        return persona
    
    return "user"
```

### Pros
✅ Always gets latest data from Keycloak  
✅ Works with custom attributes AND roles  
✅ No hardcoding  
✅ Scalable

### Cons
❌ HTTP call per query (adds latency ~50-100ms)  
❌ Requires admin credentials  
❌ More complex

### Optimization
Add caching:
```python
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=100)
def get_persona_cached(email, timestamp):
    return get_persona_from_keycloak(email)

# Use with 5-minute cache:
timestamp = datetime.now().replace(second=0, microsecond=0) // timedelta(minutes=5)
persona = get_persona_cached(email, timestamp)
```

---

## Option 4: Store in OpenWebUI Database (Hybrid)

### How it works
1. Sync persona from Keycloak to OpenWebUI's database
2. Read from OpenWebUI DB in pipeline

```python
# One-time sync or via webhook
def sync_personas_to_openwebui():
    import sqlite3
    
    personas = get_all_from_keycloak()  # From Option 3
    
    conn = sqlite3.connect('/app/backend/data/webui.db')
    for email, persona in personas.items():
        # Store in user metadata or custom table
        conn.execute(
            "UPDATE user SET metadata = ? WHERE email = ?",
            (json.dumps({"persona": persona}), email)
        )
    conn.commit()

# In pipeline
def get_persona_from_db(user_id):
    import sqlite3
    conn = sqlite3.connect('/app/backend/data/webui.db')
    cur = conn.execute("SELECT metadata FROM user WHERE id = ?", (user_id,))
    result = cur.fetchone()
    if result:
        metadata = json.loads(result[0])
        return metadata.get("persona", "user")
    return "user"
```

### Pros
✅ Fast (local database)  
✅ No external calls during queries  
✅ Scalable

### Cons
❌ Requires sync mechanism  
❌ Can be out of sync with Keycloak  
❌ More setup

---

## Recommended Approach

**For your case (2-10 users):**

### Phase 1: Email Mapping (Now)
Use Option 1 for immediate testing:
```python
PERSONA_MAP = {
    "alice.tenanta@gmail.com": "CEO",
    "diana.tenantb@gmail.com": "CEO",
}
```

### Phase 2: Keycloak API (Production)
Switch to Option 3 with caching for production.

---

## Implementation: Option 1 (Quick Start)

Add to your pipeline:

```python
class Pipe:
    # Persona assignments
    PERSONA_MAP = {
        # Tenant A
        "alice.tenanta@gmail.com": "CEO",
        "bob.manager@tenanta.com": "manager",
        "sarah.analyst@tenanta.com": "analyst",
        
        # Tenant B
        "diana.tenantb@gmail.com": "CEO",
        "john.manager@tenantb.com": "manager",
    }
    
    def get_tenant_persona(self, user_info: dict, __user__: dict = None):
        # ... existing tenant extraction ...
        
        # Get persona from map
        email = __user__.get("email", "") if __user__ else ""
        persona_id = self.PERSONA_MAP.get(email, "user")
        
        if persona_id != "user":
            print(f"[Self² AI] ✓ Mapped persona: {persona_id}")
        
        return tenant_id, persona_id
```

**Result:**
- alice.tenanta → `tenant-tenanta/CEO/`
- diana.tenantb → `tenant-tenantb/CEO/`
- bob.manager@tenanta → `tenant-tenanta/manager/`

---

## Testing Persona Isolation

Upload different files:

**As alice.tenanta (CEO):**
- Upload: `executive-summary.pdf`
- S3: `tenant-tenanta/CEO/executive-summary.pdf`
- Query: "What's the strategic plan?" → Gets CEO data only

**As bob.manager@tenanta (manager):**
- Upload: `department-report.pdf`  
- S3: `tenant-tenanta/manager/department-report.pdf`
- Query: "What's the strategic plan?" → "No access" (CEO-only data)

**Cross-persona test:**
- bob asks about CEO data → No access ✅
- alice asks about manager data → No access ✅ (unless we allow CEO to see all)

---

## Decision Matrix

| Criteria | Email Map | JWT Parse | Keycloak API | DB Sync |
|----------|-----------|-----------|--------------|---------|
| **Setup Time** | 5 min | 30 min | 1 hour | 2 hours |
| **Scalability** | Low | High | High | High |
| **Latency** | 0ms | 0ms | 50-100ms | 0ms |
| **Maintenance** | Manual | Auto | Auto | Semi-auto |
| **Our Recommendation** | ✅ Start | ⚠️ Complex | ✅ Production | Later |

**Bottom line:** Start with email mapping now, migrate to Keycloak API later.
