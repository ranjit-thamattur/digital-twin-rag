#!/bin/bash
# Cleanup Script - Flush all RAG system data
# WARNING: This will DELETE all files, vectors, and metadata!

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Digital Twin RAG - Complete Data Cleanup                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "⚠️  WARNING: This will permanently delete:"
echo "   - All files in S3 bucket"
echo "   - All vectors in Qdrant collection"
echo "   - All file records in OpenWebUI database"
echo "   - File-sync processing cache"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup..."
echo ""

# ============================================================================
# 1. Clear S3 Bucket
# ============================================================================
echo "📦 [1/4] Clearing S3 bucket..."
FILE_COUNT=$(aws --endpoint-url=http://localhost:4566 s3 ls s3://digital-twin-docs/ --recursive 2>/dev/null | wc -l || echo 0)

if [ "$FILE_COUNT" -gt 0 ]; then
    echo "   Found $FILE_COUNT files to delete"
    aws --endpoint-url=http://localhost:4566 s3 rm s3://digital-twin-docs/ --recursive
    echo "   ✅ S3 bucket cleared"
else
    echo "   ℹ️  S3 bucket already empty"
fi

# ============================================================================
# 2. Clear Qdrant Collection
# ============================================================================
echo ""
echo "🔍 [2/4] Clearing Qdrant collection..."

# Check if collection exists
COLLECTION_EXISTS=$(curl -s http://localhost:6333/collections/digital_twin_knowledge 2>/dev/null | jq -r '.status' || echo "not_found")

if [ "$COLLECTION_EXISTS" = "ok" ]; then
    POINT_COUNT=$(curl -s http://localhost:6333/collections/digital_twin_knowledge | jq -r '.result.points_count' || echo 0)
    echo "   Found $POINT_COUNT points to delete"
    
    # Delete collection
    curl -s -X DELETE http://localhost:6333/collections/digital_twin_knowledge > /dev/null
    
    # Recreate empty collection
    curl -s -X PUT http://localhost:6333/collections/digital_twin_knowledge \
      -H "Content-Type: application/json" \
      -d '{"vectors": {"size": 768, "distance": "Cosine"}}' > /dev/null
    
    echo "   ✅ Qdrant collection cleared and recreated"
else
    echo "   ℹ️  Qdrant collection doesn't exist, creating fresh..."
    curl -s -X PUT http://localhost:6333/collections/digital_twin_knowledge \
      -H "Content-Type: application/json" \
      -d '{"vectors": {"size": 768, "distance": "Cosine"}}' > /dev/null
    echo "   ✅ Fresh Qdrant collection created"
fi

# ============================================================================
# 3. Clear OpenWebUI File Database
# ============================================================================
echo ""
echo "📄 [3/5] Clearing OpenWebUI file records..."

# Count files first
FILE_DB_COUNT=$(docker exec openwebui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.execute('SELECT COUNT(*) FROM file')
print(cur.fetchone()[0])
" 2>/dev/null || echo 0)

if [ "$FILE_DB_COUNT" -gt 0 ]; then
    echo "   Found $FILE_DB_COUNT file records to delete"
    docker exec openwebui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
conn.execute('DELETE FROM file')
conn.commit()
print('✅ File table cleared')
"
else
    echo "   ℹ️  File table already empty"
fi

# ============================================================================
# 4. Delete Physical Uploaded Files
# ============================================================================
echo ""
echo "🗑️  [4/5] Deleting physical uploaded files..."

# Count files in uploads directory
UPLOAD_COUNT=$(docker exec openwebui find /app/backend/data/uploads -type f 2>/dev/null | wc -l || echo 0)

if [ "$UPLOAD_COUNT" -gt 0 ]; then
    echo "   Found $UPLOAD_COUNT physical files to delete"
    docker exec openwebui rm -rf /app/backend/data/uploads/*
    echo "   ✅ Physical files deleted"
else
    echo "   ℹ️  Upload directory already empty"
fi

# ============================================================================
# 5. Clear File-Sync Cache
# ============================================================================
echo ""
echo "🔄 [5/5] Clearing file-sync cache..."

if docker exec file-sync-dt test -f /app/backend/data/synced_files.json 2>/dev/null; then
    docker exec file-sync-dt rm -f /app/backend/data/synced_files.json
    echo "   ✅ File-sync cache cleared"
else
    echo "   ℹ️  File-sync cache already empty"
fi

# Restart file-sync to apply changes
echo "   Restarting file-sync service..."
docker restart file-sync-dt > /dev/null 2>&1
echo "   ✅ File-sync restarted"

# ============================================================================
# Verification
# ============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Cleanup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📊 Final Status:"
echo ""

# Verify S3
S3_COUNT=$(aws --endpoint-url=http://localhost:4566 s3 ls s3://digital-twin-docs/ --recursive 2>/dev/null | wc -l || echo 0)
echo "   S3 Files:        $S3_COUNT ✅"

# Verify Qdrant
QDRANT_COUNT=$(curl -s http://localhost:6333/collections/digital_twin_knowledge | jq -r '.result.points_count' || echo 0)
echo "   Qdrant Points:   $QDRANT_COUNT ✅"

# Verify OpenWebUI
WEBUI_COUNT=$(docker exec openwebui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.execute('SELECT COUNT(*) FROM file')
print(cur.fetchone()[0])
" 2>/dev/null || echo 0)
echo "   OpenWebUI Files: $WEBUI_COUNT ✅"

echo ""
echo "🎉 System is now clean and ready for fresh data!"
echo ""
