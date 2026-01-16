# Tenant Isolation Test Files - Usage Guide

## Files Created

### Tenant A (TechCorp Industries)
Located in: `/Users/ranjitt/Desktop/`

**CEO Level:**
- `tenantA-CEO-report.txt`
  - Revenue: $50,000,000
  - Highly confidential strategic data
  - CEO compensation, M&A pipeline
  - Should only be visible to CEO persona

**Manager Level:**
- `tenantA-manager-report.txt`
  - Department revenue: $8,500,000
  - Operational metrics
  - Team performance data
  - Should only be visible to manager persona

### Tenant B (GlobalRetail Corp)
Located in: `/Users/ranjitt/Desktop/`

**CEO Level:**
- `tenantB-CEO-report.txt`
  - Revenue: $10,000,000
  - Strategic overview
  - M&A activity, shareholder info
  - Should only be visible to CEO persona

**Manager Level:**
- `tenantB-manager-report.txt`
  - Marketing department data
  - Campaign performance
  - Budget allocation
  - Should only be visible to manager persona

## Testing Procedure

### 1. Clean System
```bash
cd /Users/ranjitt/Ranjit/digital-twin-rag
./scripts/cleanup-all-data.sh
```

### 2. Upload Files

**As alice.tenanta@gmail.com (TenantA CEO):**
- Upload: `tenantA-CEO-report.txt`
- Expected S3: `tenant-tenanta/CEO/tenantA-CEO-report.txt`

**As alice.manager@tenanta.com (TenantA Manager):**
- Upload: `tenantA-manager-report.txt`
- Expected S3: `tenant-tenanta/manager/tenantA-manager-report.txt`

**As diana.tenantb@gmail.com (TenantB CEO):**
- Upload: `tenantB-CEO-report.txt`
- Expected S3: `tenant-tenantb/CEO/tenantB-CEO-report.txt`

**As bob.manager@tenantb.com (TenantB Manager):**
- Upload: `tenantB-manager-report.txt`
- Expected S3: `tenant-tenantb/manager/tenantB-manager-report.txt`

### 3. Test Queries

#### Test 1: Tenant Isolation
**Query as TenantA CEO:** "What is our revenue?"
- Expected: "$50,000,000" (from TenantA CEO report)
- Should NOT see: $10,000,000 (TenantB data)

**Query as TenantB CEO:** "What is our revenue?"
- Expected: "$10,000,000" (from TenantB CEO report)
- Should NOT see: $50,000,000 (TenantA data)

#### Test 2: Persona Isolation
**Query as TenantA CEO:** "What are the strategic initiatives?"
- Expected: CEO-level data (AI Integration, Global Expansion)
- Should see: Project Phoenix, Atlas, Quantum

**Query as TenantA Manager:** "What are the strategic initiatives?"
- Expected: Manager-level data (hiring, system upgrades)
- Should NOT see: CEO-only strategic projects

#### Test 3: Cross-Tenant Queries (Should Fail)
**Query as TenantA CEO:** "What is GlobalRetail's revenue?"
- Expected: "I don't have access to that information"
- Reason: TenantB data is isolated from TenantA

#### Test 4: Cross-Persona Queries (Should Fail)
**Query as TenantA Manager:** "What is the CEO compensation?"
- Expected: "I don't have access to that information"
- Reason: CEO-level data is isolated from manager persona

### 4. Verification Commands

**Check S3 Structure:**
```bash
aws --endpoint-url=http://localhost:4566 s3 ls s3://digital-twin-docs/ --recursive
```

Expected:
```
tenant-tenanta/CEO/tenantA-CEO-report.txt
tenant-tenanta/manager/tenantA-manager-report.txt
tenant-tenantb/CEO/tenantB-CEO-report.txt
tenant-tenantb/manager/tenantB-manager-report.txt
```

**Check Qdrant Metadata:**
```bash
curl -s http://localhost:6333/collections/digital_twin_knowledge/points/scroll \
  -d '{"limit": 10, "with_payload": true}' \
  | jq '.result.points[] | {tenant: .payload.tenantId, persona: .payload.personaId}'
```

Expected:
```json
{"tenant": "tenant-tenanta", "persona": "CEO"}
{"tenant": "tenant-tenanta", "persona": "manager"}
{"tenant": "tenant-tenantb", "persona": "CEO"}
{"tenant": "tenant-tenantb", "persona": "manager"}
```

## Expected Results Summary

| User | Query | Expected Answer | Source |
|------|-------|----------------|--------|
| alice.tenanta (CEO) | What is our revenue? | $50,000,000 | TenantA CEO report |
| diana.tenantb (CEO) | What is our revenue? | $10,000,000 | TenantB CEO report |
| TenantA Manager | What is the team size? | 45 employees | TenantA manager report |
| TenantB Manager | What is the marketing spend? | $125,000 | TenantB manager report |
| TenantA CEO | TenantB revenue? | No access | Cross-tenant blocked |
| TenantA Manager | CEO compensation? | No access | Cross-persona blocked |

## Success Criteria

✅ Each tenant only sees their own data  
✅ Each persona only sees their level of data  
✅ Cross-tenant queries return "no information"  
✅ Cross-persona queries return "no information"  
✅ S3 paths include both tenant AND persona  
✅ Qdrant filters by both tenant AND persona
