# Keycloak Persona Mapper - Step-by-Step Configuration Guide

## Prerequisites

- Access to Keycloak Admin Console: `http://localhost:8080/admin`
- Admin credentials (username: `admin`, password: `admin`)
- Realm: `self2ai`
- Client: `openwebui`

## Part 1: Add Persona Attribute to Users

### Step 1: Login to Keycloak

1. Open browser: `http://localhost:8080/admin`
2. Login with:
   - **Username:** `admin`
   - **Password:** `admin`
3. Select realm: **self2ai** (dropdown top-left)

### Step 2: Add Persona to User

1. Click **Users** in left sidebar
2. Click **View all users** button
3. Find user: `diana.tenantb@gmail.com` (or any user)
4. Click on the username to edit

### Step 3: Add Attribute

1. Click **Attributes** tab (top of page)
2. You'll see a form with:
   - **Key** field (empty text box)
   - **Value** field (empty text box)
   - **Add** button

3. Fill in:
   ```
   Key:   persona
   Value: CEO
   ```

4. Click **Add** button
5. Click **Save** button (bottom of page)

### Step 4: Repeat for Other Users

**For alice.tenanta@gmail.com:**
- Attribute: `persona` = `manager`

**For bob@anywhere.com:**
- Attribute: `persona` = `user`

---

## Part 2: Configure OIDC Mapper

### Step 1: Navigate to Client

1. Click **Clients** in left sidebar
2. Find and click **openwebui** in the list
3. You're now in the Client settings page

### Step 2: Go to Client Scopes

1. Click **Client scopes** tab (top menu)
2. You'll see a section: **Assigned client scopes**
3. Look for: **openwebui-dedicated** (should have "Default" tag)
4. Click on **openwebui-dedicated** link

### Step 3: Add Mapper

1. You're now in the Client Scope detail page
2. Click **Mappers** tab (top menu)
3. Click **Add mapper** button (top right)
4. From dropdown, select **By configuration**
5. Click **User Attribute** from the list

### Step 4: Configure Mapper Form

You'll see a form with these fields. Fill exactly as shown:

```
┌─────────────────────────────────────────────────┐
│ Mapper Type:    User Attribute (auto-selected) │
├─────────────────────────────────────────────────┤
│ Name:           persona-mapper                  │
├─────────────────────────────────────────────────┤
│ User Attribute: persona                         │
├─────────────────────────────────────────────────┤
│ Token Claim Name: persona                       │
├─────────────────────────────────────────────────┤
│ Claim JSON Type:  String                        │
├─────────────────────────────────────────────────┤
│ Add to ID token:        [✓] ON                  │
├─────────────────────────────────────────────────┤
│ Add to access token:    [✓] ON                  │
├─────────────────────────────────────────────────┤
│ Add to userinfo:        [✓] ON                  │
├─────────────────────────────────────────────────┤
│ Multivalued:            [ ] OFF                 │
├─────────────────────────────────────────────────┤
│ Aggregate attribute values: [ ] OFF             │
└─────────────────────────────────────────────────┘
```

**Field Descriptions:**

- **Name:** `persona-mapper` (any name, for your reference)
- **User Attribute:** `persona` (matches the attribute key you added to users)
- **Token Claim Name:** `persona` (how it appears in JWT token)
- **Claim JSON Type:** `String` (dropdown - select String)
- **Add to ID token:** ✓ Check this box
- **Add to access token:** ✓ Check this box
- **Add to userinfo:** ✓ Check this box
- **Multivalued:** Leave unchecked
- **Aggregate attribute values:** Leave unchecked

### Step 5: Save

1. Click **Save** button at bottom
2. You should see success message
3. You'll see your new mapper in the list: **persona-mapper**

---

## Part 3: Verification

### Test 1: Check Token Claims

1. Logout any existing OpenWebUI session
2. Login again to OpenWebUI: `http://localhost:3000`
3. Login as `diana.tenantb@gmail.com`
4. Check logs:
   ```bash
   docker logs openwebui | grep persona
   ```
5. **Expected output:**
   ```
   [Self² AI] ✓ Found persona in user attributes: CEO
   ```

### Test 2: Check S3 Path

1. Upload a file as `diana.tenantb@gmail.com`
2. Check S3:
   ```bash
   aws --endpoint-url=http://localhost:4566 s3 ls \
     s3://digital-twin-docs/tenant-tenantb/ --recursive
   ```
3. **Expected:**
   ```
   tenant-tenantb/CEO/filename.txt
   ```
   (Not `tenant-tenantb/user/filename.txt`)

### Test 3: Verify Qdrant

```bash
curl -s http://localhost:6333/collections/digital_twin_knowledge/points/scroll \
  -d '{"limit": 5, "with_payload": true}' \
  | jq '.result.points[] | {tenant: .payload.tenantId, persona: .payload.personaId}'
```

**Expected:**
```json
{
  "tenant": "tenant-tenantb",
  "persona": "CEO"
}
```

---

## Troubleshooting

### Issue 1: Persona Still Shows "user"

**Check 1:** User attribute exists
```
Keycloak → Users → [User] → Attributes
Should see: persona = CEO
```

**Check 2:** Mapper is configured
```
Keycloak → Clients → openwebui → Client scopes → 
openwebui-dedicated → Mappers
Should see: persona-mapper
```

**Check 3:** Restart OpenWebUI
```bash
docker restart openwebui
```

**Check 4:** Clear browser cache and re-login

---

## Summary

**What you configured:**
1. Added `persona` attribute to Keycloak users
2. Created OIDC mapper to include persona in tokens
3. OpenWebUI pipeline now receives persona in `__user__` parameter

**Result:**
- ✅ User uploads: `tenant-tenantb/CEO/file.txt`
- ✅ Qdrant stores: `{tenantId: "tenant-tenantb", personaId: "CEO"}`
- ✅ Queries filtered by both tenant AND persona
