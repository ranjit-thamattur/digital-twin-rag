import os
import asyncio
import json
import boto3
import time
import random
import uuid
import hashlib
import threading
from typing import Optional, List
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import requests

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "172.17.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
VECTOR_SIZE = 1024

# Generation Model Configuration
# For Demo: Use Claude 3.5 Haiku (Fast/Cheap) for everything
DEFAULT_MODEL = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")

# Local Model (Ollama) Support
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() == "true"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b") # Small 3B model for speed

# Initialize FastMCP server
mcp = FastMCP("CloneMind Knowledge Base")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

from botocore.config import Config
bedrock_config = Config(
    retries={
        'max_attempts': 1,  # 1 attempt total = 0 retries. Let our custom loop handle it.
        'mode': 'standard'
    },
    connect_timeout=15,
    read_timeout=15
)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=bedrock_config)

# Rate Limiter Class
class RateLimiter:
    """Rate limiter to prevent overwhelming Bedrock API"""
    def __init__(self, calls_per_second=2):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()

# Initialize rate limiter and cache
embedding_rate_limiter = RateLimiter(calls_per_second=2)  # Conservative: 2 calls/sec
embedding_cache = {}

# Cost tracking
cost_tracker = {
    "embedding_calls": 0,
    "haiku_calls": 0,
    "sonnet_calls": 0,
    "total_tokens": 0
}

def get_text_hash(text: str) -> str:
    """Create a hash of the text for caching."""
    return hashlib.sha256(text.encode()).hexdigest()

def get_embedding(text: str, use_cache: bool = True) -> List[float]:
    """Generate embedding using Bedrock Titan with rate limiting, caching, and improved backoff."""
    
    # Check cache first
    if use_cache:
        text_hash = get_text_hash(text)
        if text_hash in embedding_cache:
            print(f"✓ Using cached embedding for text hash: {text_hash[:8]}...")
            return embedding_cache[text_hash]
    
    max_retries = 10
    base_delay = 3  # Increased base delay
    max_delay = 60  # Maximum delay cap
    
    current_model = EMBEDDING_MODEL_ID
    
    for attempt in range(max_retries):
        try:
            # Rate limit BEFORE calling Bedrock
            embedding_rate_limiter.wait()
            
            print(f"Generating embedding (Attempt {attempt+1}/{max_retries}) for text (length: {len(text)}) using model {current_model}")
            
            # Ensure text is not too long for Titan
            if len(text) > 30000:
                text = text[:30000]

            body = json.dumps({"inputText": text})
            
            try:
                response = bedrock_client.invoke_model(
                    body=body,
                    modelId=current_model,
                    accept="application/json",
                    contentType="application/json"
                )
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle model unavailability (Region/Account specific)
                if "model is not available" in error_str and current_model == "amazon.titan-embed-text-v2:0":
                    print("Titan V2 not available, falling back to V1...")
                    current_model = "amazon.titan-embed-text-v1"
                    continue  # Retry immediately with V1
                
                # Handle Throttling with improved exponential backoff
                if "throttling" in error_str or "too many requests" in error_str:
                    if attempt < max_retries - 1:
                        # More aggressive exponential backoff with jitter
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        jitter = random.uniform(0, delay * 0.3)  # 30% jitter
                        total_delay = delay + jitter
                        print(f"⚠ Bedrock Throttled. Retrying in {total_delay:.2f} seconds...")
                        time.sleep(total_delay)
                        continue
                raise

            response_body = json.loads(response.get("body").read())
            embedding = response_body.get("embedding")
            
            if not embedding:
                print(f"Error: Bedrock returned empty embedding.")
                raise Exception("Empty embedding returned from Bedrock")
            
            # Cache successful result
            if use_cache:
                text_hash = get_text_hash(text)
                embedding_cache[text_hash] = embedding
            
            # Track costs
            cost_tracker["embedding_calls"] += 1
            
            print(f"✓ Successfully generated embedding (size: {len(embedding)}) using {current_model}")
            return embedding
            
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"✗ Final Bedrock Embedding Error: {str(e)}")
                raise
            else:
                # Fallback delay for non-throttling errors
                delay = min(base_delay * (attempt + 1), max_delay)
                print(f"⚠ Transient Bedrock Error: {str(e)}. Retrying in {delay:.2f}s...")
                time.sleep(delay)
    
    raise Exception("Failed to get embedding after multiple retries")

def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks for better RAG retrieval."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    
    return chunks

def ensure_collection(collection_name: str, vector_size: int):
    """Ensure a Qdrant collection exists for the tenant."""
    try:
        if not qdrant_client.collection_exists(collection_name):
            print(f"Creating collection: {collection_name} with vector size {vector_size}")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
        else:
            # Check existing collection vector size
            col_info = qdrant_client.get_collection(collection_name)
            existing_size = col_info.config.params.vectors.size
            if existing_size != vector_size:
                print(f"WARNING: Collection {collection_name} has size {existing_size}, but we want {vector_size}!")
    except Exception as e:
        print(f"Qdrant ensure_collection error: {str(e)}")
        raise

@mcp.tool()
async def search_knowledge_base(query: str, tenantId: str, limit: Optional[int] = 5) -> str:
    """
    Search a tenant's specific collection for relevant document chunks.
    """
    try:
        collection_name = tenantId.replace("-", "_")
        
        # 1. Generate Query Vector
        vector = get_embedding(query)

        # 2. Check if collection exists
        if not qdrant_client.collection_exists(collection_name):
            return "Knowledge base for this tenant has not been initialized yet."

        # 3. Search Qdrant
        search_result = qdrant_client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=limit,
            with_payload=True
        )

        formatted_results = []
        for res in search_result:
            text = res.payload.get("text", "No text found")
            source = res.payload.get("filename", "Unknown Source")
            formatted_results.append(f"--- SOURCE: {source} ---\n{text}")

        return "\n\n".join(formatted_results) if formatted_results else "No relevant information found."
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def generate_twin_response(
    query: str, 
    tenantId: str, 
    system_prompt: str,
    messages: Optional[List[dict]] = None
) -> str:
    """
    Full RAG Pipeline: Search -> Route -> Generate.
    This replaces the previous N8N workflow.
    """
    try:
        # 1. Search Knowledge Base
        context = await search_knowledge_base(query, tenantId)
        
        # 2. Performance Tracking
        cost_tracker["haiku_calls"] += 1
        
        # 3. Handle Ollama if enabled
        if USE_OLLAMA:
            print(f"Routing to local Ollama model: {OLLAMA_MODEL}")
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": f"{system_prompt}\n\nContext:\n{context}\n\nUser: {query}",
                "stream": False
            }
            res = requests.post(f"{OLLAMA_URL}/api/generate", json=payload)
            return res.json().get("response", "Ollama Error")

        # 4. Bedrock Haiku (Standard Demo Path)
        print(f"Routing to Bedrock Haiku: {DEFAULT_MODEL}")
        
        bedrock_messages = []
        if messages:
            for msg in messages[-5:]:  # Last 5 for context
                role = "user" if msg.get("role") == "user" else "assistant"
                content = msg.get("content", "")
                if content:
                    bedrock_messages.append({"role": role, "content": [{"text": content}]})
        
        # Add current query with context formatted for better model comprehension
        rag_prompt = f"""<knowledge_context>
{context}
</knowledge_context>

Based on the knowledge context provided above, please answer the user query. 

Rules:
1. Prioritize the provided context. 
2. ALWAYS cite the source filename (e.g., [Source: filename.txt]) at the end of your answer if you used information from the context.
3. If the answer is not in the context, state that and use your general knowledge, but do not make up facts about the company.

User Query: {query}"""
        bedrock_messages.append({"role": "user", "content": [{"text": rag_prompt}]})

        # 4. Invoke Bedrock
        response = bedrock_client.invoke_model(
            modelId=DEFAULT_MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": bedrock_messages,
                "temperature": 0.7
            })
        )
        
        response_body = json.loads(response.get("body").read())
        answer = response_body["content"][0]["text"]
        
        # Track token usage if available
        if "usage" in response_body:
            cost_tracker["total_tokens"] += response_body["usage"].get("input_tokens", 0)
            cost_tracker["total_tokens"] += response_body["usage"].get("output_tokens", 0)
        
        return answer

    except Exception as e:
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

        print(f"Ingesting knowledge for tenant: {tenantId} (Length: {len(text)})")
        collection_name = tenantId.replace("-", "_")
        
        # 1. Chunk the text
        chunks = chunk_text(text, chunk_size=2000, overlap=300)
        print(f"Split text into {len(chunks)} chunks for processing.")
        
        # 2. Get embedding for the first chunk to ensure collection is created with correct size
        first_vector = get_embedding(chunks[0])
        vector_size = len(first_vector)
        ensure_collection(collection_name, vector_size)
        
        successful_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                # Use cached embedding if possible, skip first chunk as we already got it
                vector = first_vector if i == 0 else get_embedding(chunk)
                
                chunk_metadata = {
                    "text": chunk,
                    "tenantId": tenantId,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    **(metadata or {})
                }
                
                point_id = str(uuid.uuid4())
                qdrant_client.upsert(
                    collection_name=collection_name,
                    points=[models.PointStruct(id=point_id, vector=vector, payload=chunk_metadata)]
                )
                successful_chunks += 1
                
                # Small delay to keep logs clean and respect Bedrock/Qdrant
                if i % 5 == 0 and i > 0:
                    print(f"Processed {i}/{len(chunks)} chunks...")
                    await asyncio.sleep(0.1)
                
            except Exception as chunk_err:
                print(f"Error processing chunk {i}: {str(chunk_err)}")
                # Continue with other chunks even if one fails
        
        print(f"✓ Successfully ingested {successful_chunks}/{len(chunks)} chunks for {tenantId}.")
        return f"Successfully ingested {successful_chunks}/{len(chunks)} chunks for {tenantId}."
    except Exception as e:
        print(f"✗ Critical Ingestion Error: {str(e)}")
        return f"Error ingesting knowledge: {str(e)}"

@mcp.tool()
async def get_cost_stats() -> str:
    """
    Get current cost tracking statistics.
    """
    stats = f"""
Cost Tracking Statistics:
========================
Embedding API Calls: {cost_tracker['embedding_calls']}
Model Calls (Haiku/Local): {cost_tracker['haiku_calls']}
Total Tokens Processed: {cost_tracker['total_tokens']}

Estimated Costs:
- Embeddings: ~${cost_tracker['embedding_calls'] * 0.0003:.4f}
- Model Queries: ~${cost_tracker['haiku_calls'] * 0.0012:.4f}
- Total Estimated: ~${(cost_tracker['embedding_calls'] * 0.0003) + (cost_tracker['haiku_calls'] * 0.0012):.4f}

Cache Hit Rate: {len(embedding_cache)} cached embeddings
Mode: {"Ollama (Local)" if USE_OLLAMA else "Bedrock (Remote)"}
"""
    return stats

@mcp.tool()
async def clear_embedding_cache() -> str:
    """
    Clear the embedding cache (useful for memory management).
    """
    cache_size = len(embedding_cache)
    embedding_cache.clear()
    return f"Cleared {cache_size} cached embeddings."

# FastAPI HTTP Bridge for the Pipeline
@app.get("/")
async def health_check():
    return JSONResponse({
        "status": "healthy", 
        "service": "CloneMind MCP Server",
        "version": "2.0",
        "features": ["rate_limiting", "caching", "cost_tracking"]
    })

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

@app.get("/stats")
async def stats():
    """Get cost and performance statistics"""
    return JSONResponse({
        "cost_tracker": cost_tracker,
        "cache_size": len(embedding_cache),
        "estimated_cost": {
            "embeddings": round(cost_tracker['embedding_calls'] * 0.0003, 4),
            "haiku": round(cost_tracker['haiku_calls'] * 0.0012, 4),
            "sonnet": round(cost_tracker['sonnet_calls'] * 0.006, 4),
            "total": round((cost_tracker['embedding_calls'] * 0.0003) + 
                          (cost_tracker['haiku_calls'] * 0.0012) + 
                          (cost_tracker['sonnet_calls'] * 0.006), 4)
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
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("PORT", "3000"))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          CloneMind Knowledge Base MCP Server v2.0            ║
╠══════════════════════════════════════════════════════════════╣
║  Features:                                                   ║
║  ✓ Rate Limiting (2 req/sec)                                ║
║  ✓ Embedding Caching                                        ║
║  ✓ Improved Exponential Backoff                             ║
║  ✓ Cost Tracking                                            ║
║  ✓ Smart Model Routing (Haiku/Sonnet)                       ║
╠══════════════════════════════════════════════════════════════╣
║  Region: {AWS_REGION:48} ║
║  Embedding Model: {EMBEDDING_MODEL_ID:42} ║
║  Transport: {transport:50} ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if transport == "sse":
        # Run FastAPI server for SSE/HTTP mode
        print(f"Starting HTTP server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Run MCP in stdio mode
        print("Starting MCP in stdio mode...")
        mcp.run(transport="stdio")