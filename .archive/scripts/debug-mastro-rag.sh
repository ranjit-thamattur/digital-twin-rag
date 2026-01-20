#!/bin/bash
# Debug Mastro RAG - Check what context is retrieved

TENANT_ID="tenant-mastrometals"
QUERY="What 2 inch MS pipes do you have in stock?"

echo "🔍 Debugging RAG Pipeline for Mastro Metals"
echo "Query: $QUERY"
echo ""

# Step 1: Generate embedding for the query
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Generate Query Embedding"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

EMBED_RESPONSE=$(curl -s -X POST http://localhost:11434/api/embeddings \
-H "Content-Type: application/json" \
-d "{\"model\": \"nomic-embed-text\", \"prompt\": \"$QUERY\"}")

EMBEDDING=$(echo "$EMBED_RESPONSE" | jq -c '.embedding')
EMBED_DIM=$(echo "$EMBEDDING" | jq 'length')

echo "✅ Embedding generated: $EMBED_DIM dimensions"
echo ""

# Step 2: Search Qdrant
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Search Qdrant Collection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SEARCH_RESPONSE=$(curl -s -X POST "http://localhost:6333/collections/${TENANT_ID}_knowledge/points/search" \
-H "Content-Type: application/json" \
-d "{
  \"vector\": $EMBEDDING,
  \"limit\": 3,
  \"with_payload\": true,
  \"with_vector\": false
}")

echo "Search Results:"
echo "$SEARCH_RESPONSE" | jq '.result[] | {score, text: .payload.text[:200]}'
echo ""

# Step 3: Extract context
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Retrieved Context"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CONTEXT=$(echo "$SEARCH_RESPONSE" | jq -r '.result[].payload.text' | head -c 1000)
echo "$CONTEXT"
echo ""
echo "..."
echo ""

# Step 4: Test with LLM
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Generate Answer with llama3.2:1b"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PROMPT="Use the following context to answer the question. Be specific and cite details from the context.

Context:
$CONTEXT

Question: $QUERY

Answer:"

LLM_RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate \
-H "Content-Type: application/json" \
-d "{
  \"model\": \"llama3.2:1b\",
  \"prompt\": $(echo "$PROMPT" | jq -Rs .),
  \"stream\": false
}")

ANSWER=$(echo "$LLM_RESPONSE" | jq -r '.response')
echo "$ANSWER"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Diagnostic Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
