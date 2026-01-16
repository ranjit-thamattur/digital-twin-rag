# CRITICAL: How to Update OpenWebUI Functions

## The Problem

**Copying files to `/app/backend/pipelines/` DOES NOT update running code!**

OpenWebUI stores functions in its **database**, not as files. The pipeline code must be updated via the **UI**.

## Solution: Update via OpenWebUI UI

### Step 1: Access Functions

1. Open OpenWebUI: `http://localhost:3000`
2. Click **Admin Panel** (top right, gear icon)
3. Click **Functions** in left sidebar

### Step 2: Find Your Function

- Look for: **"n8n_pipeline_function"** or **"Self² AI with RAG"**
- Click on it to view/edit

### Step 3: Add PERSONA_MAP

1. Click **Edit** (pencil icon)
2. Find the `__init__` method (around line 42-46)
3. **After** `self.valves = self.Valves()`, add:

```python
    def __init__(self):
        self.type = "manifold"
        self.id = "self2ai"
        self.name = "Self² AI: "
        self.valves = self.Valves()
    
    # ADD THIS SECTION 👇
    # Persona assignments (email -> persona mapping)
    PERSONA_MAP = {
        # Tenant A users
        "alice.tenanta@gmail.com": "CEO",
        "bob.manager@tenanta.com": "manager",
        
        # Tenant B users
        "diana.tenantb@gmail.com": "CEO",
        "john.manager@tenantb.com": "manager",
    }
    # END OF NEW SECTION 👆

    def pipes(self) -> List[dict]:
        return [{"id": "self2ai_rag", "name": "Self² AI RAG"}]
```

### Step 4: Update get_tenant_persona Method

Find the `get_tenant_persona` method (around line 150-175) and replace the persona extraction with:

```python
        # Extract persona from email mapping
        if __user__:
            email = __user__.get("email", "")
            persona_id = self.PERSONA_MAP.get(email, "user")  # Default to "user"
            
            if persona_id != "user":
                print(f"[Self² AI] ✓ Mapped persona for {email}: {persona_id}")
            else:
                print(f"[Self² AI] ℹ️  No persona mapping for {email}, using default: user")

        print(f"[Self² AI] ✅ Final Assignment: {tenant_id} / {persona_id}")
        return tenant_id, persona_id
```

### Step 5: Save

1. Scroll to bottom
2. Click **Save**
3. **Done!** Changes apply immediately

### Step 6: Test

```bash
# Check logs for the mapping message
docker logs openwebui 2>&1 | grep "Mapped persona" | tail -3
```

**Expected:**
```
[Self² AI] ✓ Mapped persona for alice.tenanta@gmail.com: CEO
```

## Why File Copies Don't Work

```
/app/backend/pipelines/pipeline-dynamic.py  ← File exists here
                                            ← But NOT used!
                                            
OpenWebUI Database (webui.db)              ← Code stored here
  └─ function table                        ← THIS is what runs!
```

## Quick Verification

After saving in UI, check it worked:

```bash
# Upload a file as alice.tenanta
# Check S3 path:
aws --endpoint-url=http://localhost:4566 s3 ls \
  s3://digital-twin-docs/tenant-tenanta/

# Should see:
# tenant-tenanta/CEO/filename.txt  ✅
```

## Alternative: Import Function from File

If you have the code in a file:

1. Admin Panel → Functions
2. Click **+ Create**  
3. Select **Import from file**
4. Upload `/Users/ranjitt/Ranjit/digital-twin-rag/workflows/openwebui/pipeline-dynamic.py`
5. This creates a NEW function from the file

But editing existing function via UI is simpler!

## Bottom Line

✅ **Update via UI** - Changes apply immediately  
❌ **Don't copy files** - Doesn't update running code

File copies only work if OpenWebUI is configured to load pipelines from files (not the default).
