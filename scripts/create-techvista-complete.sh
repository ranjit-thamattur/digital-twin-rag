#!/bin/bash
# Create IT Company Tenant with Admin User

echo "🏢 Creating TechVista Solutions Tenant with Admin User..."
echo ""

# Step 1: Create Tenant
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Creating Tenant"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TENANT_RESPONSE=$(curl -s -X POST http://localhost:8000/api/tenants \
-H "Content-Type: application/json" \
-d '{
  "tenant_name": "techvista",
  "company_name": "TechVista Solutions",
  "industry": "IT Services & Software Development",
  "admin_email": "admin@techvista.com",
  "admin_password": "TechVista@2026",
  "tone": "professional",
  "special_instructions": "You are an AI assistant for TechVista Solutions, a leading IT services and software development company.\n\nCORE RESPONSIBILITIES:\n1. Technical Support - Provide specific solutions with error codes, commands, and resolution steps\n2. Project Status - Include timelines, team, budget, blockers, and next milestones\n3. Client Information - Reference contracts, SLAs, tickets, and billing details\n4. Resource Management - Track employee skills, software licenses, server inventory\n\nRESPONSE FORMAT:\n- Always cite specific data from knowledge base (versions, dates, IDs, metrics)\n- Include actionable next steps with responsible person and timeline\n- For technical issues: Root cause, solution steps (with commands), prevention\n- For projects: Status, progress %, next milestone, team, blockers\n- For clients: Current projects, SLA status, open tickets, next review\n\nTECHNICAL CONTEXT:\n- Tech Stack: Node.js, React, Python, PostgreSQL, MongoDB, Redis, AWS, Kubernetes\n- Tools: Jira, Slack, GitHub, Jenkins, Datadog\n- Provide code snippets, configuration examples, and links to internal docs\n\nPERSONA AWARENESS:\n- Developers: Technical depth, code, architecture, API docs\n- Project Managers: Status, timelines, resources, risks\n- CEO/CTO: Business impact, ROI, strategic insights\n- Support: Quick troubleshooting, runbooks, escalation paths\n\nRULES:\n- Be precise with numbers, never estimate if exact data exists\n- Never expose credentials or sensitive data\n- Every response must have clear action items\n- Include confidence level if uncertain"
}')

echo "$TENANT_RESPONSE" | jq '.'
echo ""

TENANT_ID=$(echo "$TENANT_RESPONSE" | jq -r '.id')

if [ "$TENANT_ID" = "null" ] || [ -z "$TENANT_ID" ]; then
  echo "❌ Failed to create tenant!"
  echo "Response: $TENANT_RESPONSE"
  exit 1
fi

echo "✅ Tenant created!"
echo "Tenant ID: $TENANT_ID"
echo ""

# Step 2: Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SETUP COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Tenant Details:"
echo "  Company: TechVista Solutions"
echo "  Tenant ID: $TENANT_ID"
echo "  Collection: ${TENANT_ID}_knowledge"
echo ""
echo "👤 Admin User:"
echo "  Email: admin@techvista.com"
echo "  Password: TechVista@2026"
echo "  Role: Admin"
echo ""
echo "🔐 Login URL:"
echo "  http://localhost:3000"
echo ""
echo "📝 Next Steps:"
echo "  1. Login to OpenWebUI with the admin credentials above"
echo "  2. Upload IT company knowledge base documents"
echo "  3. Test RAG queries with different personas"
echo ""
echo "💡 Example Upload:"
echo "  curl -X POST http://localhost:5678/webhook/upload-document \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{"
echo '      "fileName": "TechVista_Projects.txt",'
echo '      "content": "...",'
echo '      "metadata": {'
echo "        \"tenantId\": \"$TENANT_ID\","
echo '        "personaId": "Admin"'
echo '      }'
echo "    }'"
echo ""
