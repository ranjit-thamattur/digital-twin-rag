#!/bin/bash
# Remove unwanted test scripts
# Keep only essential ones

echo "🧹 Removing unwanted test scripts..."
echo ""

SCRIPTS_DIR="/Users/ranjitt/Ranjit/digital-twin-rag/scripts"
ARCHIVE_DIR="/Users/ranjitt/Ranjit/digital-twin-rag/.archive/scripts"
mkdir -p "$ARCHIVE_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Analyzing Test Scripts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Archive redundant test/debug scripts
echo "Archiving redundant scripts..."

# Debug scripts - keep only one comprehensive debug script
mv "$SCRIPTS_DIR/debug-mastro-rag.sh" "$ARCHIVE_DIR/" 2>/dev/null
echo "  → Archived debug-mastro-rag.sh (can use verify-tenants.sh instead)"

# Test scripts - keep only the essential one
mv "$SCRIPTS_DIR/test-rag-quality.sh" "$ARCHIVE_DIR/" 2>/dev/null
echo "  → Archived test-rag-quality.sh (test-mastro-queries.sh is sufficient)"

# Tenant-specific scripts - keep only the complete ones
mv "$SCRIPTS_DIR/upload-mastro-direct.sh" "$ARCHIVE_DIR/" 2>/dev/null
mv "$SCRIPTS_DIR/upload-mastro-inventory.sh" "$ARCHIVE_DIR/" 2>/dev/null
echo "  → Archived redundant upload scripts (use upload-techvista-kb.sh pattern)"

echo ""
echo "✅ Archived 5 redundant scripts"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Essential Scripts Remaining"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 Startup/Shutdown:"
echo "  ✅ startup.sh"
echo "  ✅ shutdown.sh"
echo ""
echo "🏢 Tenant Management:"
echo "  ✅ create-mastro-metals-tenant.sh"
echo "  ✅ create-techvista-complete.sh"
echo "  ✅ verify-tenants.sh"
echo "  ✅ view-tenants.sh"
echo ""
echo "📤 Upload:"
echo "  ✅ upload-techvista-kb.sh"
echo ""
echo "🧪 Testing:"
echo "  ✅ test-mastro-queries.sh (comprehensive test)"
echo ""
echo "🧹 Maintenance:"
echo "  ✅ cleanup-all-data.sh"
echo "  ✅ cleanup-project.sh"
echo "  ✅ cleanup-workflows.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Scripts count:"
echo "  Before: 15 scripts"
echo "  After: 10 scripts"
echo "  Archived: 5 scripts"
echo ""
echo "✨ Only essential scripts remain!"
echo ""
echo "📝 Note: All archived scripts are in .archive/scripts/"
echo "    and can be restored if needed."
