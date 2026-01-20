# TechVista Solutions - Admin Credentials

## Company Information
- **Company Name:** TechVista Solutions
- **Domain:** techvista.com
- **Industry:** IT Services & Software Development
- **Location:** Bangalore, India

---

## Admin User Credentials

### Login Details:
- **Email:** admin@techvista.com
- **Password:** TechVista@2026
- **Role:** Admin
- **Tenant ID:** Will be generated (e.g., `tenant-techvista`)

### Login URL:
- **OpenWebUI:** http://localhost:3000
- **Keycloak Admin:** http://localhost:8080/admin

---

## Collection Name:
- **Qdrant Collection:** `{tenant_id}_knowledge`
- **Example:** `tenant-techvista_knowledge`

---

## Usage Instructions:

### 1. Create Tenant & Admin:
```bash
chmod +x /Users/ranjitt/Ranjit/digital-twin-rag/scripts/create-techvista-complete.sh
/Users/ranjitt/Ranjit/digital-twin-rag/scripts/create-techvista-complete.sh
```

### 2. Login to OpenWebUI:
- Go to: http://localhost:3000
- Email: admin@techvista.com
- Password: TechVista@2026

### 3. Upload Knowledge Base:
```bash
curl -X POST http://localhost:5678/webhook/upload-document \
  -H 'Content-Type: application/json' \
  -d '{
    "fileName": "TechVista_Projects.txt",
    "content": "Project details...",
    "metadata": {
      "tenantId": "tenant-techvista",
      "personaId": "Admin"
    }
  }'
```

### 4. Test RAG Queries:
```bash
curl -X POST http://localhost:5678/webhook/openwebui \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "What projects are currently active?",
    "tenantId": "tenant-techvista",
    "personaId": "Developer"
  }'
```

---

## Security Notes:
⚠️ **Change the default password after first login!**
⚠️ **This is for development only - use strong passwords in production**

---

## Other Tenant Credentials (For Reference):

### Friday Film House:
- Email: ceo@fridayfilmhouse.com
- Password: Friday@2026
- Tenant ID: tenant-fridayfilmhouse

### Mastro Metals:
- Email: admin@mastrometals.com
- Password: Mastro@2026
- Tenant ID: tenant-mastrometals
