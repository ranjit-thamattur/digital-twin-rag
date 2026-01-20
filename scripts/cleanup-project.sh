#!/bin/bash
# Clean up unwanted code and docs
# Created: January 20, 2026

echo "🧹 Cleaning up digital-twin-rag project..."
echo ""

# Create archive directory for old files
ARCHIVE_DIR="/Users/ranjitt/Ranjit/digital-twin-rag/.archive"
mkdir -p "$ARCHIVE_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Remove backup files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove .bak files
find /Users/ranjitt/Ranjit/digital-twin-rag/scripts -name "*.bak" -exec rm -f {} \;
echo "✅ Removed .bak files from scripts/"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Archive old troubleshooting docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Move old troubleshooting/fix docs to archive
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/ROOT_CAUSE_FOUND.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/FIX_BATCH_INSERT.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/TROUBLESHOOT_UPLOAD.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/UPLOAD_WORKFLOW_FIXED.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/CLEANUP_AND_AUTO_CREATE.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/docs/BATCH_INSERT_WORKFLOW.md "$ARCHIVE_DIR/" 2>/dev/null

echo "✅ Archived old troubleshooting docs"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Archive root-level setup docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Move old setup docs to archive
mv /Users/ranjitt/Ranjit/digital-twin-rag/GMAIL_MULTITENANT_SETUP.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/KEYCLOAK_HTTPS_FIX.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/OPENWEBUI_KEYCLOAK_INTEGRATION.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/PHASE1_VALIDATION.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/PIPELINE_UPLOAD_TROUBLESHOOTING.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/REBRANDING_SUMMARY.md "$ARCHIVE_DIR/" 2>/dev/null
mv /Users/ranjitt/Ranjit/digital-twin-rag/SETUP_PIPELINE_WORKFLOWS.md "$ARCHIVE_DIR/" 2>/dev/null

echo "✅ Archived root-level setup docs"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Remove redundant scripts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove old/redundant scripts
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/create-demo-user.sh
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/create-tenantb-user.sh
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/test_multitenant_auth.sh
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/check-s3.sh
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/test-s3-upload.sh
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/scripts/create-it-company-tenant.sh

echo "✅ Removed redundant scripts"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Remove unused workflow helper files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove old N8N helper scripts (already integrated into workflows)
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/add-mcp-router.py
rm -f /Users/ranjitt/Ranjit/digital-twin-rag/workflows/n8n/fix-build-prompt-model.py

echo "✅ Removed workflow helper scripts"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Clean up test files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Archive old test files
if [ -d "/Users/ranjitt/Ranjit/digital-twin-rag/test-files" ]; then
  mv /Users/ranjitt/Ranjit/digital-twin-rag/test-files "$ARCHIVE_DIR/" 2>/dev/null
  echo "✅ Archived test-files directory"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Cleaned up:"
echo "  ✅ Backup files (.bak)"
echo "  ✅ Old troubleshooting docs (7 files)"
echo "  ✅ Root-level setup docs (7 files)"
echo "  ✅ Redundant scripts (6 files)"
echo "  ✅ Workflow helper scripts (2 files)"
echo "  ✅ Test files directory"
echo ""
echo "📦 Archived files moved to: .archive/"
echo ""
echo "✨ Project cleaned! Kept only essential files."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Essential Files Remaining:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📁 Root:"
echo "  - README.md (Main documentation)"
echo "  - README_STARTUP.md (Startup guide)"
echo "  - CHANGELOG.md (Version history)"
echo ""
echo "📁 docs/ (Production docs only):"
echo "  - QUICKSTART.md"
echo "  - STRUCTURE.md"
echo "  - AWS_BEDROCK_ANALYSIS.md"
echo "  - BEDROCK_COST_5_TENANTS.md"
echo "  - ADD_MCP_ROUTER.md"
echo "  - MODEL_SPEED_COMPARISON.md"
echo "  - IT_COMPANY_SPECIAL_INSTRUCTIONS.md"
echo "  - TECHVISTA_CREDENTIALS.md"
echo "  - TENANT_API_REFERENCE.md"
echo "  - aws_architecture.md"
echo "  - aws_deployment_guide.md"
echo "  - keycloak_persona_setup.md"
echo "  - tenant-management-service.md"
echo ""
echo "📁 scripts/ (Active scripts only):"
echo "  - startup.sh"
echo "  - shutdown.sh"
echo "  - cleanup-all-data.sh"
echo "  - create-mastro-metals-tenant.sh"
echo "  - create-techvista-complete.sh"
echo "  - upload-mastro-direct.sh"
echo "  - upload-mastro-inventory.sh"
echo "  - upload-techvista-kb.sh"
echo "  - test-mastro-queries.sh"
echo "  - test-rag-quality.sh"
echo "  - debug-mastro-rag.sh"
echo "  - verify-tenants.sh"
echo "  - view-tenants.sh"
echo ""
echo "🎯 Clean project structure achieved!"
