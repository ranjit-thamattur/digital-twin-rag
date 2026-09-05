# Digital Brain — Tenant Onboarding Guide

> This guide walks you through onboarding a new company (tenant) onto the Digital Brain platform.
> Estimated time: **15–30 minutes** per tenant.

---

## Overview — What onboarding creates

```
1. Tenant record in DynamoDB      ← who they are + plan + personas
2. Cognito user(s)                ← login credentials for the UI
3. Knowledge upload               ← their documents into Qdrant
4. Test & verify                  ← confirm the brain responds correctly
```

---

## Prerequisites

- AWS CLI configured with access to the `us-east-1` account
- SSM tunnel to the Tenant Service running on port 8000
- Access to the S3 bucket (`clonemind-docs`)

**Start the SSM tunnel:**
```bash
aws ssm start-session \
  --target i-04de122dcff25503b \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}' \
  --region us-east-1
```

---

## Step 1 — Create the Tenant

```bash
curl -X POST http://localhost:8000/api/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId":       "tenant-<companyname>",
    "companyName":    "<Company Full Name>",
    "industry":       "<Industry>",
    "plan":           "basic",
    "allowedPersonas": ["ceo", "hr", "finance"],
    "defaultPersona": "ceo"
  }'
```

**Plan options:**

| Plan | Max tokens | Use for |
|---|---|---|
| `basic` | 1,000 | Standard tenants |
| `premium` | 4,000 | High-usage tenants, complex queries |
| `enterprise` | 8,000 | Large orgs, structured output |

**Common persona sets:**

| Type of company | Suggested personas |
|---|---|
| SME / Startup | `ceo`, `hr`, `finance` |
| Coaching firm | `coach`, `ceo`, `admin` |
| Sales org | `ceo`, `sales`, `finance` |
| Full suite | `ceo`, `hr`, `finance`, `sales`, `admin`, `coach` |

**Verify it was created:**
```bash
curl http://localhost:8000/api/tenants/tenant-<companyname> | jq '{
  tenantId: .tenantId,
  company: .companyName,
  plan: .plan,
  personas: .allowedPersonas
}'
```

---

## Step 2 — Create Cognito User(s)

Create one user per person who needs login access.

```bash
curl -X POST http://localhost:8000/api/tenants/tenant-<companyname>/users \
  -H "Content-Type: application/json" \
  -d '{
    "email":      "user@company.com",
    "password":   "TempPass@2024!",
    "first_name": "First",
    "last_name":  "Last",
    "persona":    "ceo"
  }'
```

> ⚠️ The persona assigned to the user determines which Digital Brain they see on login.
> A user assigned `hr` will only interact with the HR persona's knowledge.

**Repeat for each user**, changing `email`, `first_name`, `last_name`, and `persona`.

**Verify users exist:**
```bash
curl http://localhost:8000/api/tenants/tenant-<companyname> | jq '.users'
```

---

## Step 3 — Upload Knowledge Documents

Upload documents to S3. The Lambda function will automatically trigger ingestion into Qdrant.

**S3 key format:**
```
tenant-<companyname>/<personaId>/filename.ext

Examples:
  tenant-acme/ceo/strategic-plan-2025.pdf
  tenant-acme/hr/leave-policy.docx
  tenant-acme/finance/q3-cashflow.xlsx
```

**Upload via AWS CLI:**
```bash
# Single file
aws s3 cp strategic-plan-2025.pdf \
  s3://clonemind-docs/tenant-acme/ceo/strategic-plan-2025.pdf \
  --region us-east-1

# Entire folder
aws s3 cp ./documents/ceo/ \
  s3://clonemind-docs/tenant-acme/ceo/ \
  --recursive \
  --region us-east-1
```

**Supported file types:**

| Type | Notes |
|---|---|
| `.pdf` | Must be text-based (not scanned) |
| `.docx` | Paragraphs + tables extracted |
| `.txt` / `.md` | Best quality — no parsing loss |
| `.xlsx` / `.csv` | Each sheet ingested separately |
| `.pptx` | Slide text only |

> See [`data-quality-guide.md`](./data-quality-guide.md) for full document preparation instructions.

---

## Step 4 — Verify Ingestion

After uploading, wait ~60 seconds for Lambda to process, then verify:

```bash
# Start MCP tunnel if not already running
aws ssm start-session \
  --target i-04de122dcff25503b \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}' \
  --region us-east-1

# Search for content from an uploaded doc
curl -X POST http://localhost:3000/call/search_knowledge_base \
  -H "Content-Type: application/json" \
  -d '{
    "query": "<a key phrase from one of your uploaded docs>",
    "tenantId": "tenant-<companyname>",
    "personaId": "ceo"
  }'
```

**Expected:** `results` array with relevant chunks from the uploaded document.
**If empty:** Check S3 upload succeeded and Lambda logs in CloudWatch.

---

## Step 5 — Test the Brain

Run a full end-to-end query:

```bash
curl -X POST http://localhost:3000/call/generate_twin_response \
  -H "Content-Type: application/json" \
  -d '{
    "query":      "Tell me about our growth strategy",
    "tenantId":   "tenant-<companyname>",
    "personaId":  "ceo",
    "system_prompt": "",
    "messages":   [],
    "plan":       "basic"
  }'
```

**Quality checklist for the response:**
```
□ Responds in first person ("I", "We", "Our")
□ References content from uploaded documents
□ Does NOT say "According to the documents..."
□ Does NOT fabricate specific numbers not in the docs
□ Tone matches the persona (CEO = decisive, HR = empathetic)
□ Language matches the query language
```

---

## Step 6 — Hand off to the tenant

**Give the tenant:**

1. **Login URL:** `https://ai.peakpa.com` (or your custom domain)
2. **Email + temporary password** (created in Step 2)
3. **First login instructions:**
   - Go to the login URL
   - Enter email + temp password
   - They will be prompted to set a new password on first login
4. **The data quality guide** ([`data-quality-guide.md`](./data-quality-guide.md)) so they know how to add more documents themselves

---

## Quick reference — all tenant operations

| Action | Command |
|---|---|
| List all tenants | `curl http://localhost:8000/api/tenants \| jq` |
| View specific tenant | `curl http://localhost:8000/api/tenants/tenant-id \| jq` |
| Lookup user by email | `curl "http://localhost:8000/api/user/lookup?email=user@co.com" \| jq` |
| Delete tenant knowledge | `POST /call/clear_tenant_knowledge` with `{ tenantId, personaId }` |
| Re-ingest a document | Re-upload to S3 (Lambda handles deduplication) |

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| Tenant creation fails | `tenantId` already exists | Use a different tenantId |
| User creation fails 400 | Persona not in `allowedPersonas` | Add persona to tenant first |
| Search returns empty | Lambda didn't process yet | Wait 60s, check CloudWatch |
| Search returns empty | Wrong persona | Check S3 key has correct personaId |
| PDF returns no text | Scanned / image PDF | Convert with OCR first |
| Brain gives generic answers | Docs too vague / thin | Follow data-quality-guide.md |
| Brain fabricates numbers | No matching doc chunks | Upload the relevant document |

---

## Tenant ID naming convention

```
tenant-{companyname-lowercase-no-spaces}

Examples:
  tenant-peakpa
  tenant-acmecorp
  tenant-globaltech
  tenant-smithfamily
```

Keep it short, lowercase, no special characters except hyphens.

---

*Last updated: September 2025*
