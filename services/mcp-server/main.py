import os
import asyncio
import json
import time
import uuid
import hashlib
from typing import Optional, List
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import openai

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "172.17.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding Configuration - Choose one:
# Option 1: Voyage AI (FREE 30M tokens!) - RECOMMENDED
# Option 2: OpenAI (cheap and good)
# Option 3: Cohere (has free tier)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")  # voyage, openai, or cohere

# API Keys for embedding providers
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Vector sizes by provider
VECTOR_SIZES = {
    "voyage": 1024,
    "openai": 1536,
    "cohere": 1024
}
VECTOR_SIZE = VECTOR_SIZES.get(EMBEDDING_PROVIDER, 1024)

# Initialize FastMCP server
mcp = FastMCP("CloneMind Knowledge Base")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Lazy-loaded embedding clients
voyage_client = None
cohere_client = None

# OpenAI Client (Initialized if key present)
openai_client = None
if OPENAI_API_KEY:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Caching
embedding_cache = {}

# Cost tracking
cost_tracker = {
    "embedding_calls": 0,
    "chat_calls": 0,
    "total_tokens": 0
}

def get_text_hash(text: str) -> str:
    """Create a hash of the text for caching."""
    return hashlib.sha256(text.encode()).hexdigest()

async def get_voyage_embedding(text: str) -> List[float]:
    """Generate embedding using Voyage AI (FREE 30M tokens!)"""
    global voyage_client
    if voyage_client is None:
        import voyageai
        voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    
    result = await asyncio.to_thread(
        lambda: voyage_client.embed(
            [text[:4000]], 
            model="voyage-2",
            input_type="document"
        )
    )
    return result.embeddings[0]

async def get_openai_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI with retry logic."""
    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                lambda: openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text[:8000]
                )
            )
            return response.data[0].embedding
        except Exception as e:
            if attempt == 2: raise
            wait_time = (attempt + 1) * 2
            print(f"⚠ OpenAI embedding attempt {attempt+1} failed: {str(e)}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)

async def get_cohere_embedding(text: str) -> List[float]:
    """Generate embedding using Cohere"""
    global cohere_client
    if cohere_client is None:
        import cohere
        cohere_client = cohere.Client(COHERE_API_KEY)
    
    response = await asyncio.to_thread(
        lambda: cohere_client.embed(
            texts=[text[:2048]],
            model="embed-english-v3.0",
            input_type="search_document"
        )
    )
    return response.embeddings[0]

async def get_embedding(text: str, use_cache: bool = True) -> List[float]:
    """Generate embedding using configured provider"""
    
    # Validate text is not empty
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")
    
    # Check cache first
    if use_cache:
        text_hash = get_text_hash(text)
        if text_hash in embedding_cache:
            print(f"✓ Using cached embedding for text hash: {text_hash[:8]}...")
            return embedding_cache[text_hash]
    
    print(f"Generating {EMBEDDING_PROVIDER} embedding for text (length: {len(text)})")
    
    try:
        if EMBEDDING_PROVIDER == "openai" and openai_client is None:
            raise ValueError("OpenAI API Key not configured")
            
        # Route to appropriate provider
        if EMBEDDING_PROVIDER == "voyage":
            embedding = await get_voyage_embedding(text)
        elif EMBEDDING_PROVIDER == "openai":
            embedding = await get_openai_embedding(text)
        elif EMBEDDING_PROVIDER == "cohere":
            embedding = await get_cohere_embedding(text)
        else:
            raise ValueError(f"Unknown embedding provider: {EMBEDDING_PROVIDER}")
        
        # Cache successful result
        if use_cache:
            text_hash = get_text_hash(text)
            embedding_cache[text_hash] = embedding
        
        cost_tracker["embedding_calls"] += 1
        return embedding
        
    except Exception as e:
        print(f"✗ {EMBEDDING_PROVIDER} embedding error: {str(e)}")
        # If it's a provider error, we want to know
        raise

def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    """
    Split text into chunks while trying to preserve line breaks and word boundaries.
    """
    if len(text) <= chunk_size:
        return [text]
    
    # Split by lines first to avoid cutting through sentences
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        if current_length + len(line) > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            # Keep a few lines for overlap
            overlap_lines = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk[-1:]
            current_chunk = overlap_lines + [line]
            current_length = sum(len(l) for l in current_chunk)
        else:
            current_chunk.append(line)
            current_length += len(line)
            
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
        
    return chunks

def ensure_collection(collection_name: str, vector_size: int):
    """Ensure a Qdrant collection exists for the tenant. Recreates if dimensions mismatch."""
    try:
        if not qdrant_client.collection_exists(collection_name):
            print(f"Creating collection: {collection_name} with vector size {vector_size}")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
        else:
            col_info = qdrant_client.get_collection(collection_name)
            existing_size = col_info.config.params.vectors.size
            if existing_size != vector_size:
                print(f"DIMENSION MISMATCH: Collection {collection_name} has size {existing_size}, but we want {vector_size}.")
                print(f"Recreating collection {collection_name} to match new provider...")
                qdrant_client.delete_collection(collection_name)
                qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                )
    except Exception as e:
        print(f"Qdrant ensure_collection error: {str(e)}")
        raise

@mcp.tool()
async def search_knowledge_base(query: str, tenantId: str, personaId: Optional[str] = None, limit: Optional[int] = 10) -> str:
    """
    Search a tenant's knowledge base. 
    If personaId is provided, results are strictly filtered to that persona.
    """
    if not tenantId:
        print("⚠ Search failed: No tenantId provided")
        return ""
        
    try:
        # Normalize inputs
        tenantId = tenantId.strip().lower()
        personaId = personaId.strip() if (personaId and str(personaId).strip()) else None
        
        collection_name = tenantId.replace("-", "_")
        
        # Smart Query Expansion: If the query is just 1-2 words, expand it
        search_query = query
        if len(query.split()) <= 4:
            search_query = f"{query} financial metrics revenue performance {tenantId}"

        print(f"🔍 [SEARCH] Tenant: {tenantId} | Persona: {personaId or 'Global/Any'} | Query: {search_query}")
        
        # Generate Query Vector
        vector = await get_embedding(search_query)

        # Build Persona Filter (if personaId is specifically provided)
        query_filter = None
        if personaId:
            # We filter for the specific persona OR global documents (if any)
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="personaId",
                        match=models.MatchValue(value=personaId)
                    )
                ]
            )

        # Search Qdrant
        search_result = await asyncio.to_thread(
            lambda: qdrant_client.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=limit,
                with_payload=True,
                query_filter=query_filter
            )
        )

        formatted_results = []
        for i, res in enumerate(search_result):
            text = res.payload.get("text", "No text found")
            source = res.payload.get("filename", "Unknown Source")
            score = getattr(res, 'score', 0)
            preview = text[:60].replace('\n', ' ')
            print(f"  - Hit #{i+1}: {source} [Score: {score:.4f}] | Preview: {preview}...")
            formatted_results.append(f"DOCUMENT: {source}\nCONTENT: {text}\n---")

        if not formatted_results:
            print(f"⚠ [SEARCH] Zero results found in collection {collection_name} for query: {search_query}")
            return ""

        return "\n\n".join(formatted_results)
    except Exception as e:
        print(f"✗ [SEARCH] Error: {str(e)}")
        return f"SEARCH_ERROR: {str(e)}"

@mcp.tool()
async def inspect_tenant_knowledge(tenantId: str) -> str:
    """Diagnostic tool to check the status of a tenant's knowledge base."""
    try:
        collection_name = tenantId.replace("-", "_")
        exists = qdrant_client.collection_exists(collection_name)
        
        if not exists:
            return f"Collection '{collection_name}' does not exist."
            
        info = qdrant_client.get_collection(collection_name)
        count = qdrant_client.count(collection_name).count
        
        return f"""
Knowledge Base Inspection: {tenantId}
====================================
Collection Name: {collection_name}
Vector Size: {info.config.params.vectors.size}
Distance Metric: {info.config.params.vectors.distance}
Total Document Chunks: {count}
Status: {'Empty' if count == 0 else 'Active'}
"""
    except Exception as e:
        return f"Inspection Error: {str(e)}"

@mcp.tool()
async def generate_twin_response(
    query: str, 
    tenantId: str, 
    system_prompt: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None
) -> str:
    """Full RAG Pipeline with Persona Isolation"""
    try:
        # 1. Search Knowledge Base (filtered by persona)
        context = await search_knowledge_base(query, tenantId, personaId=personaId)
        
        if openai_client is None:
            return "MCP Error: OpenAI API client not initialized. Check OPENAI_API_KEY."

        print(f"Routing to OpenAI GPT-4o-mini for response generation")
        
        # 3. Formulate the High-Premium 'AI Twin' prompt
        if context.startswith("SEARCH_ERROR"):
            rag_context_block = f"Note: There was a technical error retrieving your records: {context}"
        elif not context:
            rag_context_block = "Note: No specific records found for this query in your knowledge base."
        else:
            rag_context_block = context

        openai_messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history
        if messages:
            for msg in messages[-5:]:  # Last 5 for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    openai_messages.append({"role": role, "content": content})
        
        # Add current query with the 'AI Twin' persona instructions
        persona_label = personaId if personaId else "Digital Twin"
        
        rag_prompt = f"""Role: You are acting as the Digital Twin of the user's persona ([Persona: {persona_label}]). 
Your goal is to answer questions using the knowledge provided, while maintaining the professional tone and expertise reflected in the context.

Retrieved Wisdom (Your Memory):
{rag_context_block}

Current Discussion:
{query}

Execution Rules:
1. PERSPECTIVE: Speak in the first person ("I", "We", "Our") as if you are the Twin itself.
2. VERACITY: Use the 'Retrieved Wisdom' as your primary memory. If a specific figure, date, or fact is there, use it precisely.
3. CITATIONS: When you use data from a specific document, append a subtle reference like (Ref: filename) at the end of the sentence.
4. THE KNOWLEDGE GAP: If your 'Retrieved Wisdom' is silent on a topic, say: "Based on my current records, I don't have those specific details on hand. However, my general understanding suggests..."
5. FORMATTING: Use tables or bullet points for numerical data to make it extremely readable.
"""
        
        openai_messages.append({"role": "user", "content": rag_prompt})

        # 4. Invoke OpenAI with retry logic
        for attempt in range(2):
            try:
                response = await asyncio.to_thread(
                    lambda: openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        max_tokens=2048,
                        messages=openai_messages,
                        temperature=0.1
                    )
                )
                answer = response.choices[0].message.content
                
                # Track token usage
                if response.usage:
                    cost_tracker["total_tokens"] += response.usage.total_tokens
                
                return answer
            except Exception as e:
                if attempt == 1: raise
                print(f"⚠ Chat completion attempt {attempt+1} failed: {str(e)}. Retrying...")
                await asyncio.sleep(1)

    except Exception as e:
        print(f"✗ OpenAI error: {str(e)}")
        return f"MCP Error generating response: {str(e)}"

@mcp.tool()
async def ingest_knowledge(text: str, tenantId: str, metadata: Optional[dict] = None) -> str:
    """
    Ingest information into a tenant's private collection.
    Automatically chunks large text for better RAG performance.
    """
    try:
        if not text or not text.strip():
            print("Warning: Received empty text for ingestion")
            return "Error: Text content is empty."

        # Normalize tenantId
        tenantId = tenantId.strip().lower()
        print(f"Ingesting knowledge for tenant: {tenantId} (Length: {len(text)})")
        collection_name = tenantId.replace("-", "_")
        
        # 1. Chunk the text
        chunks = chunk_text(text, chunk_size=2000, overlap=300)
        print(f"Split text into {len(chunks)} chunks for processing.")
        
        # 2. Generate embedding for first chunk
        first_vector = await get_embedding(chunks[0])
        vector_size = len(first_vector)
        ensure_collection(collection_name, vector_size)
        
        successful_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                # Generate embedding
                vector = await get_embedding(chunk)
                
                chunk_metadata = {
                    "text": chunk,
                    "tenantId": tenantId,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "full_text_hash": get_text_hash(text)[:16],
                    **(metadata or {})
                }
                
                # Force ID normalization in metadata
                chunk_metadata["tenantId"] = tenantId
                if "personaId" in chunk_metadata and chunk_metadata["personaId"]:
                    chunk_metadata["personaId"] = str(chunk_metadata["personaId"]).strip()
                
                point_id = str(uuid.uuid4())
                await asyncio.to_thread(
                    lambda: qdrant_client.upsert(
                        collection_name=collection_name,
                        points=[models.PointStruct(id=point_id, vector=vector, payload=chunk_metadata)]
                    )
                )
                successful_chunks += 1
                
                if i % 5 == 0 and i > 0:
                    print(f"  - Ingested {i}/{len(chunks)} chunks...")
            except Exception as chunk_err:
                print(f"  - Error processing chunk {i}: {str(chunk_err)}")
                continue
        
        print(f"✓ Successfully ingested {successful_chunks}/{len(chunks)} chunks for {tenantId}.")
        return f"Successfully ingested {successful_chunks}/{len(chunks)} chunks for {tenantId}."
    except Exception as e:
        print(f"✗ Critical Ingestion Error: {str(e)}")
        return f"Error ingesting knowledge: {str(e)}"

@mcp.tool()
async def get_cost_stats() -> str:
    """Get current cost tracking statistics."""
    
    # Cost estimates
    embedding_costs = {
        "voyage": 0.0001,  # FREE for first 30M tokens!
        "openai": 0.00002,
        "cohere": 0.001
    }
    
    embedding_cost = cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0)
    chat_cost = cost_tracker['chat_calls'] * 0.001  # Claude 3.5 Haiku
    
    stats = f"""
Cost Tracking Statistics:
========================
Embedding Provider: {EMBEDDING_PROVIDER.upper()}
Chat Provider: OpenAI GPT-4o-mini

API Calls:
- Embedding Calls: {cost_tracker['embedding_calls']}
- Chat Calls: {cost_tracker['chat_calls']}
- Total Tokens Processed: {cost_tracker['total_tokens']}

Estimated Costs:
- Embeddings ({EMBEDDING_PROVIDER}): ~${embedding_cost:.4f}
- Chat (GPT-4o-mini): ~${chat_cost:.4f}
- Total Estimated: ~${embedding_cost + chat_cost:.4f}

Cache Hit Rate: {len(embedding_cache)} cached embeddings
Your OpenAI Credits: Being used! ✅
"""
    return stats

@mcp.tool()
async def clear_embedding_cache() -> str:
    """Clear the embedding cache."""
    cache_size = len(embedding_cache)
    embedding_cache.clear()
    return f"Cleared {cache_size} cached embeddings."

# FastAPI HTTP Bridge
@app.get("/")
async def health_check():
    return JSONResponse({
        "status": "healthy", 
        "service": "CloneMind MCP Server",
        "version": "3.1-openai",
        "features": ["openai_gpt4o_mini", f"{EMBEDDING_PROVIDER}_embeddings", "caching"],
        "chat_provider": "OpenAI GPT-4o-mini",
        "embedding_provider": EMBEDDING_PROVIDER
    })

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

@app.get("/stats")
async def stats():
    """Get cost and performance statistics"""
    embedding_costs = {"voyage": 0.0001, "openai": 0.00002, "cohere": 0.001}
    
    return JSONResponse({
        "cost_tracker": cost_tracker,
        "cache_size": len(embedding_cache),
        "chat_provider": "OpenAI GPT-4o-mini",
        "embedding_provider": EMBEDDING_PROVIDER,
        "estimated_cost": {
            "embeddings": round(cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0), 4),
            "chat": round(cost_tracker['chat_calls'] * 0.00015, 4), # GPT-4o-mini is cheaper
            "total": round((cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0)) + 
                          (cost_tracker['chat_calls'] * 0.00015), 4)
        }
    })

@app.post("/call/{tool_name}")
async def call_tool_bridge(tool_name: str, request: Request):
    """HTTP bridge to call MCP tools"""
    try:
        arguments = await request.json()
        
        if tool_name == "generate_twin_response":
            result = await generate_twin_response(**arguments)
        elif tool_name == "search_knowledge_base":
            result = await search_knowledge_base(**arguments)
        elif tool_name == "ingest_knowledge":
            result = await ingest_knowledge(**arguments)
        elif tool_name == "get_cost_stats":
            result = await get_cost_stats()
        elif tool_name == "clear_embedding_cache":
            result = await clear_embedding_cache()
        else:
            return JSONResponse(
                {"error": f"Tool {tool_name} not found"}, 
                status_code=404
            )
        
        return JSONResponse({"content": result})
    except Exception as e:
        import traceback
        print(f"Error in call_tool_bridge: {traceback.format_exc()}")
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("PORT", "3000"))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     CloneMind Knowledge Base MCP Server v3.0-OpenAI          ║
╠══════════════════════════════════════════════════════════════╣
║  Features:                                                   ║
║  ✓ OpenAI GPT-4o-mini (Chat)                                ║
║  ✓ {EMBEDDING_PROVIDER.upper()} Embeddings{' ' * (48 - len(EMBEDDING_PROVIDER))}║
║  ✓ Fast Response (<1 second)                                ║
║  ✓ Embedding Caching                                        ║
║  ✓ Cost Tracking                                            ║
╠══════════════════════════════════════════════════════════════╣
║  Chat: OpenAI GPT-4o-mini                                    ║
║  Embeddings: {EMBEDDING_PROVIDER:48} ║
║  Vector Size: {VECTOR_SIZE:50} ║
║  Transport: {transport:50} ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if transport == "sse":
        print(f"Starting HTTP server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        print("Starting MCP in stdio mode...")
        mcp.run(transport="stdio")