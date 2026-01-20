# Tenant Service - Quick Reference Commands

## View All Tenants

### Basic List:
```bash
curl http://localhost:8000/api/tenants | jq
```

### Formatted View:
```bash
curl -s http://localhost:8000/api/tenants | jq -r '.[] | "\(.company_name) (\(.tenant_id)) - \(.industry)"'
```

### Or use the script:
```bash
./scripts/view-tenants.sh
```

---

## View Specific Tenant

### Get MedPlus Details:
```bash
curl http://localhost:8000/api/tenants/tenant-medplus | jq
```

### Get Tenant with Users:
```bash
curl "http://localhost:8000/api/tenants/tenant-medplus" | jq '{
  company: .company_name,
  users: .users | map(.email),
  personas: .personas | map(.persona_name)
}'
```

---

## View Users

### All Users:
```bash
curl http://localhost:8000/api/tenants | jq -r '.[] | .users[]? | "\(.email) - \(.persona)"'
```

### MedPlus Users Only:
```bash
curl http://localhost:8000/api/tenants/tenant-medplus | jq '.users'
```

---

## Lookup User by Email

### Check if User Exists:
```bash
curl "http://localhost:8000/api/user/lookup?email=ranjit.t@medplus.com" | jq
```

### Get User's Tenant & Persona:
```bash
curl -s "http://localhost:8000/api/user/lookup?email=ranjit.t@medplus.com" | jq '{
  found: .found,
  tenant: .tenantId,
  persona: .personaId,
  company: .companyName
}'
```

---

## Get Tenant Prompts (for N8N)

### Get MedPlus Prompts:
```bash
curl http://localhost:8000/api/prompts/tenant-medplus | jq
```

### Get CEO Persona Prompt:
```bash
curl -s http://localhost:8000/api/prompts/tenant-medplus | jq '.personas.CEO'
```

---

## Admin Portal UI

### Open Admin UI:
```bash
open http://localhost:8000/admin
```

This provides:
- ✅ Visual tenant list
- ✅ Add/edit tenants
- ✅ Add/edit users
- ✅ Assign personas
- ✅ Configure prompts

---

## Quick Stats

### Count Everything:
```bash
echo "Tenants: $(curl -s http://localhost:8000/api/tenants | jq 'length')"
echo "Total Users: $(curl -s http://localhost:8000/api/tenants | jq '[.[] | .users[]?] | length')"
```

### List All Tenants:
```bash
curl -s http://localhost:8000/api/tenants | jq -r '.[] | .company_name'
```

---

## Useful Aliases

Add to your `~/.zshrc`:

```bash
alias tenants='curl -s http://localhost:8000/api/tenants | jq'
alias tenant-users='curl -s http://localhost:8000/api/tenants | jq -r ".[] | .users[]? | \"\(.email) - \(.persona)\""'
alias lookup-user='function _lookup(){ curl -s "http://localhost:8000/api/user/lookup?email=$1" | jq; }; _lookup'
```

Then use:
```bash
tenants                                    # List all tenants
tenant-users                               # List all users
lookup-user ranjit.t@medplus.com          # Lookup specific user
```

---

## Example Outputs

### List Tenants:
```json
[
  {
    "tenant_id": "tenant-medplus",
    "company_name": "MedPlus Healthcare",
    "industry": "Healthcare & Medical",
    "tone": "professional and empathetic",
    "is_active": true
  }
]
```

### Lookup User:
```json
{
  "found": true,
  "tenantId": "tenant-medplus",
  "personaId": "CEO",
  "companyName": "MedPlus Healthcare",
  "email": "ranjit.t@medplus.com"
}
```

### Get Prompts:
```json
{
  "tenantId": "tenant-medplus",
  "companyName": "MedPlus Healthcare",
  "industry": "Healthcare & Medical",
  "tone": "professional and empathetic",
  "personas": {
    "CEO": {
      "focus": "strategic decisions and organizational vision",
      "style": "executive summary with key insights",
      "additionalContext": "Emphasize business impact and ROI"
    }
  }
}
```

---

**All tenant operations available via API!** 🚀
