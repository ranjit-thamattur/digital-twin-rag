#!/bin/bash
# Clean up workflows directory
# Created: January 20, 2026

echo "🧹 Cleaning up workflows directory..."
echo ""

WORKFLOWS_DIR="/Users/ranjitt/Ranjit/digital-twin-rag/workflows"
ARCHIVE_DIR="/Users/ranjitt/Ranjit/digital-twin-rag/.archive/workflows"
mkdir -p "$ARCHIVE_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Cleaning N8N Workflows"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Remove backup/old workflow files
echo "Removing backup workflow files..."
rm -f "$WORKFLOWS_DIR/n8n/"*.bak
rm -f "$WORKFLOWS_DIR/n8n/"*.backup
rm -f "$WORKFLOWS_DIR/n8n/"*.old
echo "✅ Removed .bak, .backup, .old files"

echo ""
echo "Archiving helper scripts..."
# Archive Python helper scripts (already integrated)
mv "$WORKFLOWS_DIR/n8n/update-chat-rag.py" "$ARCHIVE_DIR/" 2>/dev/null
mv "$WORKFLOWS_DIR/n8n/update-upload-workflow.py" "$ARCHIVE_DIR/" 2>/dev/null
mv "$WORKFLOWS_DIR/n8n/fix-chat-rag-collections.sh" "$ARCHIVE_DIR/" 2>/dev/null
mv "$WORKFLOWS_DIR/n8n/BUILD_PROMPT_UPDATED.js" "$ARCHIVE_DIR/" 2>/dev/null
echo "✅ Archived helper scripts"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Final N8N Workflow Structure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Essential files kept:"
echo ""
echo "📁 workflows/n8n/"
echo "  ✅ Digital Twin - Chat RAG (Multi-tenant).json"
echo "  ✅ Digital Twin - Upload (Multi-tenant).json"
echo "  ✅ mcp-model-router.js (MCP code)"
echo "  ✅ check-create-collection.js (Auto-create code)"
echo "  ✅ tenant-prompts.json (Example prompts)"
echo ""
echo "📁 workflows/openwebui/"
echo "  ✅ RAG Pipeline files"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Removed:"
echo "  ✅ 3 backup files (.bak, .backup, .old)"
echo "  ✅ 4 helper scripts (archived)"
echo ""
echo "Kept:"
echo "  ✅ 2 N8N workflow JSONs (production)"
echo "  ✅ 2 JavaScript code files (MCP router, collection check)"
echo "  ✅ 1 Example config (tenant-prompts.json)"
echo ""
echo "✨ Workflows directory cleaned!"
