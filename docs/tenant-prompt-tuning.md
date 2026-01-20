# Tenant-Specific Prompt Tuning

## Overview

The RAG system now supports **tenant-specific prompts** for customized AI responses based on the company/tenant.

## Features

✅ **Per-Tenant System Prompts** - Each tenant gets a customized system message  
✅ **Industry-Specific Tone** - Technical, strategic, or executive-focused  
✅ **Company Context** - Includes company name and industry in responses  
✅ **Response Style** - Customized formatting and metrics inclusion  

## Configuration

Edit `workflows/n8n/tenant-prompts.json` to customize prompts per tenant:

```json
{
  "tenant-tenanta": {
    "company_name": "TechCorp Industries",
    "tone": "professional and technical",
    "system_prompt": "Custom prompt for TechCorp...",
    "response_style": {
      "format": "direct and data-driven",
      "include_metrics": true
    }
  }
}
```

## Tenant Configurations

### TechCorp Industries (tenant-tenanta)
- **Tone:** Professional and technical
- **Focus:** Financial data and metrics
- **Style:** Direct, data-driven responses

### GlobalTech Solutions (tenant-tenantb)
- **Tone:** Strategic and executive-focused
- **Focus:** Business impact and market positioning
- **Style:** Strategic insights with executive summary

### DemoTech Corporation (tenant-demotenant)
- **Tone:** Clear and demonstration-focused
- **Focus:** Key metrics and achievements
- **Style:** Clear, concise, demo-friendly

## How It Works

1. **Query arrives** with `tenantId` from pipeline
2. **N8N Build Prompt** node selects tenant-specific prompt
3. **LLM receives** customized system message
4. **Response** matches tenant's tone and style

## Example Differences

**TechCorp (Technical):**
```
Q: What's our revenue?
A: TechCorp Industries generated $50,000,000 in total revenue for FY 2024, 
   with operating expenses of $35,000,000 and a net profit of $15,000,000.
```

**GlobalTech (Strategic):**
```
Q: What's our revenue?
A: GlobalTech Solutions achieved $50M in revenue this quarter, positioning us 
   for continued market leadership. This represents strong execution against 
   our strategic expansion goals.
```

**DemoTech (Demo-friendly):**
```
Q: What's our revenue?
A: Our Q1 2024 revenue was $2.5 million with 25 active clients.
```

## Adding New Tenants

1. **Add to** `workflows/n8n/tenant-prompts.json`:
```json
"tenant-newcompany": {
  "company_name": "New Company Inc",
  "industry": "Finance",
  "tone": "formal and regulatory-compliant",
  "system_prompt": "You are an AI assistant for New Company Inc..."
}
```

2. **Update N8N workflow** to import new configuration
3. **Test** with sample queries

## Best Practices

### System Prompt Guidelines:
- ✅ Start with company context
- ✅ Include specific instructions for data handling
- ✅ Define tone and style
- ✅ Address confidentiality concerns
- ✅ Specify response format

### Tone Options:
- **Technical**: For engineering/IT teams
- **Strategic**: For executives/leadership
- **Operational**: For day-to-day management
- **Financial**: For finance/accounting teams
- **Customer-facing**: For sales/support teams

## Testing

Test each tenant's prompt:

```bash
# Test TechCorp prompt
curl -X POST http://localhost:5678/webhook/chat \
  -d '{"query": "What is our revenue?", "tenantId": "tenant-tenanta"}'

# Test GlobalTech prompt
curl -X POST http://localhost:5678/webhook/chat \
  -d '{"query": "What is our revenue?", "tenantId": "tenant-tenantb"}'
```

## Performance Considerations

- Prompts are loaded in N8N workflow (no external API calls)
- No performance impact on query latency
- Can be updated without system restart
- A/B testing friendly

## Future Enhancements

- [ ] Persona-specific prompts (CEO vs Manager)
- [ ] Dynamic prompt loading from database
- [ ] Prompt versioning and rollback
- [ ] A/B testing framework
- [ ] Analytics on prompt effectiveness

## Migration from Generic Prompts

Old (generic):
```javascript
const systemMessage = "You are an AI assistant..."
```

New (tenant-specific):
```javascript
const tenantPrompts = {...};
const systemMessage = tenantPrompts[tenantId] || tenantPrompts['default'];
```

No breaking changes - falls back to default prompt if tenant not configured.
