#!/bin/bash
# Upload TechVista Knowledge Base

echo "📤 Uploading TechVista Knowledge Base to N8N..."
echo ""

# Read the file content
KNOWLEDGE_BASE=$(cat /Users/ranjitt/Ranjit/digital-twin-rag/data/techvista-knowledge-base.txt)

# Upload to N8N
curl -X POST http://localhost:5678/webhook/upload-document \
  -H 'Content-Type: application/json' \
  -d "{
    \"fileName\": \"TechVista_Knowledge_Base.txt\",
    \"content\": $(echo "$KNOWLEDGE_BASE" | jq -Rs .),
    \"metadata\": {
      \"tenantId\": \"tenant-techvista\",
      \"personaId\": \"Admin\"
    }
  }"

echo ""
echo ""
echo "✅ Upload complete!"
echo ""
echo "📊 Document Details:"
echo "  File: TechVista_Knowledge_Base.txt"
echo "  Size: $(wc -c < /Users/ranjitt/Ranjit/digital-twin-rag/data/techvista-knowledge-base.txt) bytes"
echo "  Lines: $(wc -l < /Users/ranjitt/Ranjit/digital-twin-rag/data/techvista-knowledge-base.txt)"
echo "  Tenant: tenant-techvista"
echo "  Collection: tenant-techvista_knowledge"
echo ""
