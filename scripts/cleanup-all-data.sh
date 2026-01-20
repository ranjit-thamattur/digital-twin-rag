#!/bin/bash
# Complete Data Cleanup - S3, Qdrant, OpenWebUI

echo "🧹 Starting complete data cleanup..."
echo ""

# 1. Clean S3 (LocalStack)
echo "1️⃣ Cleaning S3..."
aws --endpoint-url=http://localhost:4566 s3 rm s3://digital-twin-docs --recursive 2>/dev/null && echo "  ✅ S3 contents deleted" || echo "  ℹ️  Bucket empty or doesn't exist"
echo "  ℹ️  Bucket preserved (not deleting bucket itself)"

# 2. Clean Qdrant collection
echo ""
echo "2️⃣  Cleaning Qdrant..."

# Delete all collections
for collection in $(curl -s http://localhost:6333/collections | jq -r '.result.collections[].name'); do
  curl -X DELETE http://localhost:6333/collections/$collection 2>/dev/null && echo "  ✅ Deleted: $collection"
done

echo "  ✅ All Qdrant collections deleted"

# 3. Clean OpenWebUI data
echo ""
echo "3️⃣ Cleaning OpenWebUI data..."
docker exec openwebui rm -rf /app/backend/data/cache/* 2>/dev/null && echo "  ✅ OpenWebUI cache cleared" || echo "  ⚠️  Could not clear cache"
docker exec openwebui rm -rf /app/backend/data/uploads/* 2>/dev/null && echo "  ✅ OpenWebUI uploads cleared" || echo "  ⚠️  Could not clear uploads"
echo "  ℹ️  Chat history preserved (delete manually if needed)"

# 4. Restart services (NOT localstack to preserve S3 bucket!)
echo ""
echo "4️⃣ Restarting services..."
docker restart qdrant
docker restart openwebui
docker restart file-sync-dt

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Wait 30 seconds for services to restart"
echo "2. S3 bucket still exists, just empty"
echo "3. Qdrant collections deleted - will auto-create on upload"
echo "4. Upload your files to start fresh"
echo ""
