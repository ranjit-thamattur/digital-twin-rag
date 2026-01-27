import os
import asyncio
import json
import time
import uuid
import hashlib
from typing import Optional, List
from mcp.server.fastmcp import FastMCP
import qdrant_client
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

# Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")

# API Keys for embedding providers
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Vector sizes by provider
VECTOR_SIZES = {
    "voyage": 1024,
    "openai": 1536,
    "cohere": 1024
}
VECTOR_SIZE = VECTOR_SIZES.get(EMBEDDING_PROVIDER, 1536)

# Initialize FastMCP server
mcp = FastMCP("CloneMind Knowledge Base")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant = qdrant_client.QdrantClient(
    host=QDRANT_HOST, 
    port=QDRANT_PORT,
    timeout=30,
    prefer_grpc=False # Use HTTP for better compatibility in ECS bridges
)

# Lazy-loaded embedding clients
voyage_client = None
cohere_client = None

# OpenAI Client
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
    """Generate embedding using Voyage AI"""
    global voyage_client
    if voyage_client is None:
        import voyageai
        voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    
    result = await asyncio.to_thread(
        lambda: voyage_client.embed([text[:4000]], model="voyage-2", input_type="document")
    )
    return result.embeddings[0]

async def get_openai_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI"""
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
    
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")
    
    if use_cache:
        text_hash = get_text_hash(text)
        if text_hash in embedding_cache:
            print(f"✓ Using cached embedding")
            return embedding_cache[text_hash]
    
    print(f"Generating {EMBEDDING_PROVIDER} embedding for text (length: {len(text)})")
    
    try:
        if EMBEDDING_PROVIDER == "openai" and openai_client is None:
            raise ValueError("OpenAI API Key not configured")
            
        if EMBEDDING_PROVIDER == "voyage":
            embedding = await get_voyage_embedding(text)
        elif EMBEDDING_PROVIDER == "openai":
            embedding = await get_openai_embedding(text)
        elif EMBEDDING_PROVIDER == "cohere":
            embedding = await get_cohere_embedding(text)
        else:
            raise ValueError(f"Unknown embedding provider: {EMBEDDING_PROVIDER}")
        
        if use_cache:
            embedding_cache[get_text_hash(text)] = embedding
        
        cost_tracker["embedding_calls"] += 1
        return embedding
        
    except Exception as e:
        print(f"✗ {EMBEDDING_PROVIDER} embedding error: {str(e)}")
        raise

def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    """Split text into chunks"""
    if len(text) <= chunk_size:
        return [text]
    
    lines = text.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        if current_length + len(line) > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
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
    """Ensure a Qdrant collection exists"""
    try:
        if not qdrant.collection_exists(collection_name):
            print(f"Creating collection: {collection_name} with vector size {vector_size}")
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
        else:
            col_info = qdrant.get_collection(collection_name)
            existing_size = col_info.config.params.vectors.size
            if existing_size != vector_size:
                print(f"DIMENSION MISMATCH: Recreating collection {collection_name}")
                qdrant.delete_collection(collection_name)
                qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                )
    except Exception as e:
        print(f"Qdrant error: {str(e)}")
        raise

@mcp.tool()
async def search_knowledge_base(query: str, tenantId: str, personaId: Optional[str] = None, limit: Optional[int] = 10) -> str:
    """Search tenant's knowledge base"""
    if not tenantId or not query or not query.strip():
        print(f"⚠ Skipping search: No tenantId or empty query")
        return ""
        
    try:
        # Skip OpenWebUI background tasks
        if len(query.strip()) < 2:
            return "" # Skip very short noise

        tenantId = tenantId.strip().lower()
        
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any']
        persona_raw = str(personaId).strip().lower() if personaId else None
        active_persona = persona_raw if (persona_raw and persona_raw not in ignored_personas) else None
        
        collection_name = tenantId.replace("-", "_")
        
        search_query = query
        if len(query.split()) <= 4:
            search_query = f"The {query} and key metrics or performance data"

        print(f"🔍 [SEARCH] Tenant: {tenantId} | Persona: {active_persona or 'OFF'} | Query: '{search_query[:50]}...'")
        
        vector = await get_embedding(search_query)

        query_filter = None
        if active_persona:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="personaId",
                        match=models.MatchValue(value=active_persona)
                    )
                ]
            )

        # ✅ HIGH-COMPATIBILITY SEARCH: Dynamic parameter detection
        def execute_search():
            # Method 1: Standard Search (modern)
            if hasattr(qdrant, 'search'):
                try:
                    # Try standard query_vector
                    return qdrant.search(
                        collection_name=collection_name,
                        query_vector=vector,
                        limit=limit,
                        with_payload=True,
                        query_filter=query_filter
                    )
                except TypeError as e:
                    # Fallback to 'query' or 'vector' if 'query_vector' fails
                    if "query_vector" in str(e):
                        return qdrant.search(
                            collection_name=collection_name,
                            query=vector,
                            limit=limit,
                            with_payload=True,
                            query_filter=query_filter
                        )
                    raise e
            # Method 2: Query Points (latest API)
            elif hasattr(qdrant, 'query_points'):
                return qdrant.query_points(
                    collection_name=collection_name,
                    query=vector,
                    limit=limit,
                    with_payload=True,
                    query_filter=query_filter
                ).points
            else:
                raise AttributeError("Qdrant client has no search capability.")

        search_result = await asyncio.to_thread(execute_search)

        formatted_results = []
        for i, res in enumerate(search_result):
            text = res.payload.get("text", "No text found")
            source = res.payload.get("filename", "Unknown Source")
            score = getattr(res, 'score', 0)
            print(f"  - Hit #{i+1}: {source} [Score: {score:.4f}]")
            formatted_results.append(f"DOCUMENT: {source}\nCONTENT: {text}\n---")

        if not formatted_results:
            print(f"⚠ [SEARCH] Zero results found")
            return ""

        return "\n\n".join(formatted_results)
    except Exception as e:
        print(f"✗ [SEARCH] Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return f"SEARCH_ERROR: {str(e)}"

@mcp.tool()
async def generate_twin_response(
    query: str, 
    tenantId: str, 
    system_prompt: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None
) -> str:
    """Full RAG Pipeline"""
    try:
        context = await search_knowledge_base(query, tenantId, personaId=personaId)
        
        if openai_client is None:
            return "MCP Error: OpenAI API client not initialized."

        print(f"Routing to OpenAI GPT-4o-mini")
        
        if context.startswith("SEARCH_ERROR"):
            rag_context_block = f"Note: Error retrieving records: {context}"
        elif not context:
            rag_context_block = "Note: No specific records found in your knowledge base."
        else:
            rag_context_block = context

        openai_messages = [{"role": "system", "content": system_prompt}]
        
        if messages:
            for msg in messages[-5:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    openai_messages.append({"role": role, "content": content})
        
        persona_label = personaId if personaId else "Digital Twin"
        
        rag_prompt = f"""Role: You are the Digital Twin ([Persona: {persona_label}]). 

Retrieved Wisdom:
{rag_context_block}

Current Discussion:
{query}

Rules:
1. Speak in first person ("I", "We", "Our")
2. Use Retrieved Wisdom precisely
3. Cite sources: (Ref: filename)
4. If no data: "Based on my records, I don't have those details..."
5. Format data with tables/bullets
"""
        
        openai_messages.append({"role": "user", "content": rag_prompt})

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
                
                if response.usage:
                    cost_tracker["total_tokens"] += response.usage.total_tokens
                    cost_tracker["chat_calls"] += 1
                
                return answer
            except Exception as e:
                if attempt == 1: raise
                print(f"⚠ Retry after error: {str(e)}")
                await asyncio.sleep(1)

    except Exception as e:
        print(f"✗ OpenAI error: {str(e)}")
        return f"MCP Error: {str(e)}"

@mcp.tool()
async def ingest_knowledge(text: str, tenantId: str, metadata: Optional[dict] = None) -> str:
    """Ingest knowledge"""
    try:
        if not text or not text.strip():
            return "Error: Text is empty"

        tenantId = tenantId.strip().lower()
        print(f"Ingesting for {tenantId} ({len(text)} chars)")
        collection_name = tenantId.replace("-", "_")
        
        chunks = chunk_text(text, chunk_size=2000, overlap=300)
        print(f"Split into {len(chunks)} chunks")
        
        first_vector = await get_embedding(chunks[0])
        vector_size = len(first_vector)
        ensure_collection(collection_name, vector_size)
        
        successful_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                vector = await get_embedding(chunk)
                
                chunk_metadata = {
                    "text": chunk,
                    "tenantId": tenantId.lower(),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "full_text_hash": get_text_hash(text)[:16],
                    **(metadata or {})
                }
                
                if "personaId" in chunk_metadata and chunk_metadata["personaId"]:
                    chunk_metadata["personaId"] = str(chunk_metadata["personaId"]).strip().lower()
                
                point_id = str(uuid.uuid4())
                
                # ✅ FIXED: Direct call, no asyncio.to_thread
                qdrant.upsert(
                    collection_name=collection_name,
                    points=[models.PointStruct(id=point_id, vector=vector, payload=chunk_metadata)]
                )
                
                successful_chunks += 1
                
                if i % 5 == 0 and i > 0:
                    print(f"  - Ingested {i}/{len(chunks)}")
                    
            except Exception as chunk_err:
                print(f"  - Error chunk {i}: {str(chunk_err)}")
                continue
        
        print(f"✓ Ingested {successful_chunks}/{len(chunks)} chunks")
        return f"Successfully ingested {successful_chunks}/{len(chunks)} chunks"
    except Exception as e:
        print(f"✗ Ingestion error: {str(e)}")
        return f"Error: {str(e)}"

@mcp.tool()
async def get_cost_stats() -> str:
    """Get cost statistics"""
    embedding_costs = {"voyage": 0.0001, "openai": 0.00002, "cohere": 0.001}
    
    embedding_cost = cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0)
    chat_cost = cost_tracker['chat_calls'] * 0.00015
    
    return f"""
Cost Statistics:
===============
Embedding Provider: {EMBEDDING_PROVIDER.upper()}
Chat Provider: OpenAI GPT-4o-mini

- Embedding Calls: {cost_tracker['embedding_calls']}
- Chat Calls: {cost_tracker['chat_calls']}
- Total Tokens: {cost_tracker['total_tokens']}

Estimated Costs:
- Embeddings: ${embedding_cost:.4f}
- Chat: ${chat_cost:.4f}
- Total: ${embedding_cost + chat_cost:.4f}

Cache: {len(embedding_cache)} embeddings
"""

@mcp.tool()
async def clear_embedding_cache() -> str:
    """Clear cache"""
    cache_size = len(embedding_cache)
    embedding_cache.clear()
    return f"Cleared {cache_size} cached embeddings"

# FastAPI HTTP Bridge
@app.get("/")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "service": "CloneMind MCP",
        "version": "3.2-fixed",
        "provider": EMBEDDING_PROVIDER
    })

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

@app.get("/stats")
async def stats():
    embedding_costs = {"voyage": 0.0001, "openai": 0.00002, "cohere": 0.001}
    
    return JSONResponse({
        "cost_tracker": cost_tracker,
        "cache_size": len(embedding_cache),
        "estimated_cost": {
            "embeddings": round(cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0), 4),
            "chat": round(cost_tracker['chat_calls'] * 0.00015, 4),
            "total": round((cost_tracker['embedding_calls'] * embedding_costs.get(EMBEDDING_PROVIDER, 0)) + 
                          (cost_tracker['chat_calls'] * 0.00015), 4)
        }
    })

@app.post("/call/{tool_name}")
async def call_tool_bridge(tool_name: str, request: Request):
    """HTTP bridge"""
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
            return JSONResponse({"error": f"Tool not found"}, status_code=404)
        
        return JSONResponse({"content": result})
    except Exception as e:
        import traceback
        print(f"Error: {traceback.format_exc()}")
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("PORT", "3000"))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       CloneMind MCP Server v3.2-FIXED                        ║
╠══════════════════════════════════════════════════════════════╣
║  ✓ OpenAI GPT-4o-mini (Chat)                                ║
║  ✓ {EMBEDDING_PROVIDER.upper()} Embeddings                  ║
║  ✓ Qdrant Search FIXED                                      ║
║  ✓ Persona Filtering                                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if transport == "sse":
        print(f"Starting HTTP server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")