# Tenant Management Service - Complete Guide

## 🎯 **Overview**

A complete tenant management system for the Digital Twin RAG platform with:
- **REST API** for tenant CRUD operations
- **Admin Portal UI** for managing tenants
- **Keycloak Integration** - Auto-create users
- **PostgreSQL Database** - Store tenant configurations
- **Dynamic Prompts** - Load from database

---

## 🏗️ **Architecture**

```
┌──────────────────┐
│  Admin Portal    │ (Browser UI)
│  :8000/admin     │
└────────┬─────────┘
         │
         ↓ HTTP
┌──────────────────┐
│ Tenant Service   │ (FastAPI)
│     :8000        │
└────┬──────┬──────┘
     │      │
     ↓      ↓
┌─────┐  ┌────────┐
│ DB  │  │Keycloak│
└─────┘  └────────┘
```

---

## 📊 **Database Schema**

### **tenants** table
- `tenant_id` (PK) - tenant-companyname
- `company_name` - Display name
- `industry` - Business domain
- `tone` - AI response tone
- `special_instructions` - Custom prompts
- `is_active` - Status flag

### **personas** table
- `tenant_id` (FK)
- `persona_name` - CEO, manager, analyst
- `focus` - What to emphasize
- `style` - Response format
- `additional_context` - Extra instructions

### **tenant_users** table
- `tenant_id` (FK)
- `email` - User email
- `persona` - Assigned role
- `keycloak_user_id` - Keycloak ID

---

## 🚀 **Quick Start**

### 1. Start Tenant Service
```bash
cd /Users/ranjitt/Ranjit/digital-twin-rag/deployment/docker
docker compose up -d tenant-service
```

### 2. Access Admin Portal
Open browser: **http://localhost:8000/admin**

### 3. Create First Tenant
- Click "➕ Create New Tenant"
- Fill form:
  - Tenant Name: `acmecorp`
 - Company Name: `ACME Corporation`
  - Industry: `Manufacturing`
  - Admin Email: `admin@acmecorp.com`
  - Password: `Acme@2024`
- Click "Create Tenant"

### 4. User Can Login!
- Go to: http://localhost:3000
- Click "Sign in with Keycloak"
- Login: `admin@acmecorp.com` / `Acme@2024`
- Start chatting!

---

## 🔌 **API Endpoints**

### Create Tenant
```bash
POST http://localhost:8000/api/tenants
Content-Type: application/json

{
  "tenant_name": "acmecorp",
  "company_name": "ACME Corporation",
  "industry": "Manufacturing",
  "tone": "professional and technical",
  "special_instructions": "Focus on operational efficiency and cost reduction.",
  "admin_email": "admin@acmecorp.com",
  "admin_password": "Acme@2024"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "tenant-acmecorp",
  "message": "Tenant 'acmecorp' created successfully",
  "admin_user": "admin@acmecorp.com",
  "login_url": "http://localhost:3000"
}
```

### List All Tenants
```bash
GET http://localhost:8000/api/tenants
```

### Get Tenant Details
```bash
GET http://localhost:8000/api/tenants/{tenant_id}
```

### Update Tenant
```bash
PUT http://localhost:8000/api/tenants/{tenant_id}
Content-Type: application/json

{
  "company_name": "ACME Corp Updated",
  "tone": "strategic and executive-focused"
}
```

### Add User to Tenant
```bash
POST http://localhost:8000/api/tenants/{tenant_id}/users
Content-Type: application/json

{
  "email": "john.manager@acmecorp.com",
  "password": "Manager@2024",
  "first_name": "John",
  "last_name": "Doe",
  "persona": "manager"
}
```

### Get Prompt Config (for N8N)
```bash
GET http://localhost:8000/api/prompts/{tenant_id}
```

**Response:**
```json
{
  "tenantId": "tenant-acmecorp",
  "companyName": "ACME Corporation",
  "industry": "Manufacturing",
  "tone": "professional and technical",
  "specialInstructions": "Focus on operational efficiency",
  "personas": {
    "CEO": {
      "focus": "strategic decisions",
      "style": "executive summary",
      "additionalContext": "Emphasize business impact"
    }
  }
}
```

---

## 🔄 **Integration with N8N**

Update your N8N "Build Prompt" node to load from API:

```javascript
// Load tenant config from API
const tenantId = buildNode.json.tenantId;
const personaId = buildNode.json.personaId;

const configResponse = await fetch(`http://tenant-service-dt:8000/api/prompts/${tenantId}`);
const config = await configResponse.json();

// Build prompt dynamically
const systemPrompt = `You are an AI assistant for ${config.companyName}, a ${config.industry} company.

Be ${config.tone} in your responses.

${config.specialInstructions}

For ${personaId} persona: ${config.personas[personaId]?.additionalContext || ''}`;

// Rest of prompt building logic...
```

---

## 🎨 **Admin Portal Features**

### Current
- ✅ List all tenants with status
- ✅ Create new tenant + admin user
- ✅ Activate/Deactivate tenants
- ✅ Beautiful responsive UI

### Coming Soon
- [ ] Edit tenant details
- [ ] View tenant analytics
- [ ] Manage users per tenant
- [ ] Add/edit personas
- [ ] Custom prompt templates
- [ ] Bulk operations

---

## 🔐 **What Happens When You Create a Tenant**

1. **Tenant record** created in database
2. **Admin user** created in Keycloak
3. **Default personas** (CEO, manager, analyst) created
4. **User mapping** added to PERSONA_MAP
5. **Ready to use immediately!**

---

## 💡 **Usage Examples**

### Scenario 1: New Customer Onboarding
```bash
# Sales team creates tenant
curl -X POST http://localhost:8000/api/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_name": "newcustomer",
    "company_name": "New Customer Inc",
    "industry": "Retail",
    "admin_email": "admin@newcustomer.com",
    "admin_password": "Welcome@2024"
  }'

# Customer can login immediately!
```

### Scenario 2: Add More Users
```bash
# Add manager
curl -X POST http://localhost:8000/api/tenants/tenant-newcustomer/users \
  -H "Content-Type: application/json" \
  -d '{
    "email": "manager@newcustomer.com",
    "password": "Manager@2024",
    "first_name": "Jane",
    "last_name": "Manager",
    "persona": "manager"
  }'
```

### Scenario 3: Customize Prompts
```bash
# Update tenant-specific instructions
curl -X PUT http://localhost:8000/api/tenants/tenant-newcustomer \
  -H "Content-Type: application/json" \
  -d '{
    "special_instructions": "Always mention our core values: Innovation, Customer First, Excellence"
  }'
```

---

## 🧪 **Testing**

```bash
# 1. Start service
docker compose up -d tenant-service

# 2. Check health
curl http://localhost:8000/

# 3. Create test tenant
curl -X POST http://localhost:8000/api/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_name": "testco",
    "company_name": "Test Company",
    "industry": "Testing",
    "admin_email": "test@test.com",
    "admin_password": "Test@2024",
    "tone": "professional"
  }'

# 4. List tenants
curl http://localhost:8000/api/tenants

# 5. Get tenant config
curl http://localhost:8000/api/prompts/tenant-testco
```

---

## 📝 **Next Steps**

1. ✅ **Deploy:** `docker compose up -d tenant-service`
2. ✅ **Access:** http://localhost:8000/admin
3. ✅ **Create tenants** via UI
4. ✅ **Update N8N** to load prompts from API
5. ✅ **Test** with new tenant

---

## 🎯 **Benefits**

✅ **No Code Changes** - Add tenants via UI/API  
✅ **Keycloak Integration** - Auto-create users  
✅ **Centralized Management** - One place for all tenants  
✅ **Dynamic Prompts** - Load from database  
✅ **Scalable** - Support unlimited tenants  
✅ **API First** - Integrate with any system  

**You now have a complete SaaS-ready tenant management system!** 🚀
