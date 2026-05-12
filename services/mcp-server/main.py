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
import redis
import boto3
import pandas as pd
import io
import docx
import pdfplumber
from pptx import Presentation as PptxPresentation

# New Bedrock & Local Embedding imports
from sentence_transformers import SentenceTransformer
import torch

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "172.17.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
REDIS_HOST = os.getenv("REDIS_HOST", "172.17.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
# CACHE_COLLECTION = "semantic_cache" # Deleted in favor of dynamic persona-based cache collections

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local") # now defaulting to local mpnet

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "bedrock")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
REWRITE_MODEL = os.getenv("REWRITE_MODEL", "mistral.ministral-3-14b-instruct")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cohere.rerank-v3-5:0")

# API Keys for embedding providers
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Vector sizes by provider
VECTOR_SIZES = {
    "local": 768,   # all-mpnet-base-v2
    "voyage": 1024,
    "openai": 1536,
    "cohere": 1024
}
VECTOR_SIZE = VECTOR_SIZES.get(EMBEDDING_PROVIDER, 768)

# Initialize FastMCP server
mcp = FastMCP("Peak AI 1.0 Knowledge Base")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant = qdrant_client.QdrantClient(
    host=QDRANT_HOST, 
    port=QDRANT_PORT,
    timeout=30,
    prefer_grpc=False # Use HTTP for better compatibility in ECS bridges
)

# Bedrock Client
bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)

# Lazy-loaded embedding models
voyage_client = None
cohere_client = None
local_embed_model = None

# OpenAI Client (Legacy/Fallback)
openai_client = None
if OPENAI_API_KEY:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Redis Client for Semantic Cache values
print(f"📡 Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    decode_responses=True,
    socket_timeout=2.0,
    socket_connect_timeout=2.0,
    retry_on_timeout=True
)

try:
    # Quick check
    redis_client.ping()
    print("✅ Redis connection successful")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")

# DynamoDB Configuration
TENANT_TABLE = os.getenv("TENANT_TABLE", "clonemind-tenants")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
tenant_metadata_table = dynamodb.Table(TENANT_TABLE)

# Caching
embedding_cache = {}

# Cost tracking
cost_tracker = {
    "embedding_calls": 0,
    "chat_calls": 0,
    "total_tokens": 0,
    "cache_hits": 0
}

# Global debug log for cache operations
cache_debug_log = []

# ─────────────────────────────────────────────
# BASIC PLAN: Off-topic / Casual Chat Guardrail
# ─────────────────────────────────────────────
OFF_TOPIC_PATTERNS = [
    "tell me a joke", "write a poem", "write a story", "what is 2+2",
    "who is your favourite", "what's the weather", "weather today",
    "hello there", "what can you do", "write an email to my friend",
    "translate this", "play a game", "what are your hobbies",
    "who are you", "what are you", "do you like", "can you sing",
    "give me a recipe", "what is the meaning of life", "tell me something fun",
    "entertain me", "make me laugh", "write a rap", "write a poem"
]

BUSINESS_KEYWORDS = [
    "revenue", "strategy", "client", "pipeline", "kpi", "report",
    "growth", "forecast", "budget", "market", "product", "team",
    "project", "risk", "compliance", "customer", "sales", "performance",
    "invoice", "contract", "partner", "roadmap", "target", "objective",
    "stakeholder", "quarter", "annual", "profit", "cost", "headcount",
    "hiring", "onboard", "workflow", "process", "sla", "metrics", "data",
    "analysis", "insight", "dashboard", "document", "policy", "procedure",
    "peak", "profile", "company"
]

BASIC_GUARDRAIL_RESPONSE = (
    "I'm your business AI Twin and I'm focused on helping you with "
    "work-related queries. Please ask me something related to your "
    "company, strategy, clients, or knowledge base. 💼"
)

def is_off_topic(query: str, tenant_keywords: Optional[List[str]] = None) -> bool:
    """Returns True if the query is casual/off-topic for a Basic plan tenant."""
    q = query.lower().strip()
    
    # Merge global business keywords with tenant-specific ones
    all_business_keywords = BUSINESS_KEYWORDS
    if tenant_keywords:
        all_business_keywords = list(set(BUSINESS_KEYWORDS + [k.lower() for k in tenant_keywords]))

    # Block explicit casual patterns
    if any(p in q for p in OFF_TOPIC_PATTERNS):
        return True
    # Very short query with no business keywords → likely casual
    if len(q.split()) <= 2 and not any(k in q for k in all_business_keywords):
        return True
    return False

async def get_tenant_metadata(tenantId: str) -> dict:
    """Retrives metadata for a tenant from Redis cache or DynamoDB."""
    cache_key = f"tenant:{tenantId}:metadata"
    
    # 1. Try Redis cache
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        print(f"⚠ Redis cache fetch failed for metadata: {e}")

    # 2. Fetch from DynamoDB
    try:
        response = await asyncio.to_thread(
            lambda: tenant_metadata_table.get_item(Key={'tenantId': tenantId})
        )
        metadata = response.get('Item', {})
        
        # 3. Cache in Redis for 1 hour
        if metadata:
            try:
                redis_client.setex(cache_key, 3600, json.dumps(metadata))
            except Exception as e:
                print(f"⚠ Failed to cache tenant metadata in Redis: {e}")
        
        return metadata
    except Exception as e:
        print(f"❌ Failed to fetch tenant metadata from DynamoDB: {e}")
        return {}
# ─────────────────────────────────────────────


def get_text_hash(text: str) -> str:
    """Create a hash of the text for caching."""
    return hashlib.sha256(text.encode()).hexdigest()

def get_local_embedding(text: str) -> List[float]:
    """Generate embedding using local sentence-transformers (all-mpnet-base-v2)."""
    global local_embed_model
    if local_embed_model is None:
        print("📥 Initializing local embedding model (all-mpnet-base-v2)...")
        local_embed_model = SentenceTransformer('all-mpnet-base-v2')
    
    # model.encode returns a numpy array, convert to list
    embedding = local_embed_model.encode(text)
    return embedding.tolist()

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
        elif EMBEDDING_PROVIDER == "local":
            # Run local embedding in a thread to not block the event loop
            embedding = await asyncio.to_thread(get_local_embedding, text)
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

def robust_qdrant_search(collection_name: str, vector: list, limit: int = 1, score_threshold: float = None, query_filter: any = None):
    """Helper to perform search across different Qdrant client versions."""
    try:
        # Method 1: Modern search()
        if hasattr(qdrant, 'search'):
            return qdrant.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True
            )
        # Method 2: query_points() (Latest API)
        elif hasattr(qdrant, 'query_points'):
            response = qdrant.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True
            )
            return response.points
        else:
            raise AttributeError("Qdrant client has no search or query_points method")
    except TypeError as e:
        # If query_vector fails, try 'query' (older versions)
        if "query_vector" in str(e) and hasattr(qdrant, 'search'):
            return qdrant.search(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True
            )
        raise e

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

async def get_semantic_cache(query: str, tenantId: str, personaId: Optional[str] = None) -> Optional[str]:
    """Check if a semantically similar question exists in the persona-specific cache."""
    try:
        tenantId = tenantId.strip().lower()
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any', 'user']
        persona_raw = str(personaId).strip().lower() if personaId else None
        active_persona = persona_raw if (persona_raw and persona_raw not in ignored_personas) else "global"
        
        # Clean query: strip markdown noise (* and _) and whitespace for better matching
        clean_query = query.strip().strip('*').strip('_').strip()
        if not clean_query: clean_query = query
        
        # ✅ PERSONA-BASED CACHE COLLECTION
        cache_collection = f"{tenantId.replace('-', '_')}_{active_persona}_cache"
        
        vector = await get_embedding(clean_query)
        ensure_collection(cache_collection, len(vector))
        
        # Search for similar questions (Strict Isolation by Collection Name)
        results = await asyncio.to_thread(
            robust_qdrant_search,
            collection_name=cache_collection,
            vector=vector,
            limit=1,
            score_threshold=0.96  # Increased from 0.88 to prevent over-matching
        )
        
        log_entry = {
            "query": clean_query[:50] + "...",
            "collection": cache_collection,
            "timestamp": time.time(),
            "hit": False
        }

        if results:
            score = results[0].score
            cache_id = results[0].payload.get("cache_id")
            log_entry["score"] = round(score, 4)
            
            if cache_id:
                try:
                    response = redis_client.get(f"cache:{cache_id}")
                    if response:
                        log_entry["hit"] = True
                        log_entry["reason"] = "OK"
                        cache_debug_log.append(log_entry)
                        cost_tracker["cache_hits"] += 1
                        return response
                    else:
                        log_entry["reason"] = "Redis key missing/expired"
                except Exception as redis_err:
                    log_entry["reason"] = f"Redis error: {str(redis_err)}"
            else:
                log_entry["reason"] = "No cache_id in vector payload"
        else:
            log_entry["score"] = 0
            log_entry["reason"] = "No match above 0.96"
        
        cache_debug_log.append(log_entry)
        if len(cache_debug_log) > 20: cache_debug_log.pop(0)
        return None

    except Exception as e:
        cache_debug_log.append({
            "event": "error",
            "error": str(e),
            "query": query[:50],
            "timestamp": time.time()
        })
        print(f"⚠ Cache lookup error: {str(e)}")
        return None

async def save_to_semantic_cache(query: str, answer: str, tenantId: str, personaId: Optional[str] = None):
    """Store question vector and answer in persona-specific cache."""
    try:
        tenantId = tenantId.strip().lower()
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any', 'user']
        persona_raw = str(personaId).strip().lower() if personaId else None
        active_persona = persona_raw if (persona_raw and persona_raw not in ignored_personas) else "global"
        
        # Clean query: strip markdown noise (* and _) and whitespace for better matching
        clean_query = query.strip().strip('*').strip('_').strip()
        if not clean_query: clean_query = query
        
        # ✅ PERSONA-BASED CACHE COLLECTION
        cache_collection = f"{tenantId.replace('-', '_')}_{active_persona}_cache"
        
        vector = await get_embedding(clean_query)
        ensure_collection(cache_collection, len(vector))
        
        cache_id = str(uuid.uuid4())
        
        # Store metadata in Qdrant
        payload = {
            "query": query,
            "tenantId": tenantId.lower(),
            "personaId": active_persona,
            "cache_id": cache_id,
            "created_at": time.time()
        }
        
        qdrant.upsert(
            collection_name=cache_collection,
            points=[models.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload)]
        )
        
        # Store full answer in Redis (TTL: 24 hours)
        redis_client.setex(f"cache:{cache_id}", 86400, answer)
        print(f"💾 [CACHE SAVE] Collection: {cache_collection}")
    except Exception as e:
        print(f"⚠ Cache save error: {str(e)}")

async def clear_semantic_cache_for_tenant(tenantId: str):
    """Wipe all semantic cache collections for a specific tenant."""
    try:
        tenantId = tenantId.strip().lower()
        prefix = tenantId.replace("-", "_")
        
        # Get all collections
        collections_response = qdrant.get_collections()
        deleted_count = 0
        
        for col in collections_response.collections:
            name = col.name
            if name.startswith(f"{prefix}_") and name.endswith("_cache"):
                print(f"🧹 Deleting cache collection: {name}")
                qdrant.delete_collection(name)
                deleted_count += 1
        
        # Also clear in-memory embedding cache
        embedding_cache.clear()
        print("🧼 Flushing in-memory vector cache")
        
        return True
    except Exception as e:
        print(f"⚠ Cache clear error: {str(e)}")
        return False

@mcp.tool()
async def search_knowledge_base(
    query: str, 
    tenantId: str = "", 
    limit: int = 5, 
    personaId: str = "ceo", 
    filename: Optional[str] = None,
    return_raw: bool = False
) -> any:
    """Search the knowledge base for a specific tenant and persona. Use 'filename' to restrict search to a specific document."""
    if not tenantId or not query or not query.strip():
        return "Please provide both tenantId and a search query."
        
    try:
        # 1. Clean inputs
        tenantId = tenantId.strip().lower()
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any', 'user']
        persona_raw = str(personaId).strip().lower() if personaId else "ceo"
        active_persona = persona_raw if persona_raw not in ignored_personas else "global"
        
        # 2. Collection Name
        collection_name = f"{tenantId.replace('-', '_')}_{active_persona}"
        
        # 3. Handle Contextual References
        # If the query contains "this sheet", "it", "that document" and a filename is provided, 
        # we treat the filename as the primary filter.
        context_words = ["this sheet", "this document", "that sheet", "the file", "the sheet", "it"]
        is_contextual = any(word in query.lower() for word in context_words)
        
        search_query = query
        if len(query.split()) <= 4:
            search_query = f"The {query} and key metrics or performance data"

        print(f"🔍 [SEARCH] Collection: {collection_name} | Persona: {active_persona} | Filename Filter: {filename} | Query: '{search_query[:50]}...'")
        
        vector = await get_embedding(search_query)

        # 4. Build Filter (STRICT ISOLATION)
        must_filters = [
            models.FieldCondition(
                key="personaId",
                match=models.MatchValue(value=active_persona)
            )
        ]
        
        # Add Filename filter if provided
        if filename:
            must_filters.append(
                models.FieldCondition(
                    key="filename",
                    match=models.MatchValue(value=filename)
                )
            )
            
        query_filter = models.Filter(must=must_filters)

        # 5. Execute Search
        search_result = await asyncio.to_thread(
            robust_qdrant_search,
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            query_filter=query_filter
        )

        formatted_results = []
        for i, res in enumerate(search_result):
            text = res.payload.get("text", "No text found")
            source = res.payload.get("filename") or res.payload.get("fileName") or res.payload.get("source") or "Unknown Document"
            sheet = res.payload.get("sheet_name")
            hit_persona = res.payload.get("personaId", "None")
            score = getattr(res, 'score', 0)
            
            print(f"  - Hit #{i+1}: {source} {'['+sheet+']' if sheet else ''} [Score: {score:.4f}]")
            
            citation = f"DOCUMENT: {source}"
            if sheet:
                citation += f" [SHEET: {sheet}]"
            
            formatted_results.append(f"{citation} (Persona: {hit_persona})\nCONTENT: {text}\n---")

        if not formatted_results and active_persona != "global" and not filename:
            # Fallback to global ONLY if no filename filter was used
            print(f"⚠ [SEARCH] No results. Falling back to global.")
            global_collection = f"{tenantId.replace('-', '_')}_global"
            if qdrant.collection_exists(global_collection):
                global_filter = models.Filter(
                    must=[models.FieldCondition(key="personaId", match=models.MatchValue(value="global"))]
                )
                search_result = await asyncio.to_thread(
                    robust_qdrant_search,
                    collection_name=global_collection,
                    vector=vector,
                    limit=limit,
                    query_filter=global_filter
                )
            for res in search_result:
                text = res.payload.get("text", "")
                source = res.payload.get("filename", "Global Source")
                formatted_results.append(f"DOCUMENT: {source} (Persona: global)\nCONTENT: {text}\n---")

        if return_raw:
            return search_result
            
        if not formatted_results:
            return ""
            
        return "\n".join(formatted_results)
    except Exception as e:
        # Graceful handling for missing collections or temporary issues
        error_msg = str(e).lower()
        if "not found" in error_msg or "does not exist" in error_msg:
            print(f"⚠ [SEARCH] Collection '{collection_name}' not found. Returning empty results.")
            return ""
        
        print(f"✗ [SEARCH] Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return f"SEARCH_ERROR: {str(e)}"

async def rewrite_query(original_query: str) -> str:
    """Use Mistral on Bedrock to rewrite/optimize the query for RAG."""
    try:
        prompt = f"Rewrite this search query to be more descriptive and optimized for a vector search engine. Only return the rewritten query text: {original_query}"
        
        body = json.dumps({
            "prompt": f"<s>[INST] {prompt} [/INST]",
            "max_tokens": 128,
            "temperature": 0.1
        })
        
        response = await asyncio.to_thread(
            lambda: bedrock_runtime.invoke_model(
                modelId=REWRITE_MODEL,
                contentType="application/json",
                accept="application/json",
                body=body
            )
        )
        
        response_body = json.loads(response.get('body').read())
        rewritten = response_body.get('outputs', [{}])[0].get('text', original_query).strip()
        print(f"🔄 [REWRITE] '{original_query}' -> '{rewritten}'")
        return rewritten
    except Exception as e:
        print(f"⚠ [REWRITE] Error: {e}")
        return original_query

async def rerank_results(query: str, hits: List[any], top_n: int = 5) -> List[any]:
    """Use Cohere Rerank on Bedrock to pick the most relevant chunks."""
    if not hits: return []
    try:
        documents = [hit.payload.get("text", "") for hit in hits]
        
        body = json.dumps({
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "api_version": 1
        })
        
        response = await asyncio.to_thread(
            lambda: bedrock_runtime.invoke_model(
                modelId=RERANK_MODEL,
                contentType="application/json",
                accept="application/json",
                body=body
            )
        )
        
        response_body = json.loads(response.get('body').read())
        results = response_body.get('results', [])
        
        # Map original hits back to reranked order
        ranked_hits = []
        for r in results:
            idx = r.get('index')
            if idx < len(hits):
                ranked_hits.append(hits[idx])
        
        print(f"🎯 [RERANK] Reduced {len(hits)} hits to top {len(ranked_hits)}")
        return ranked_hits
    except Exception as e:
        print(f"⚠ [RERANK] Error: {e}")
        return hits[:top_n]

async def call_bedrock_claude(system_prompt: str, messages: List[dict], max_tokens: int) -> str:
    """Invoke Claude 4.5 Sonnet on Bedrock."""
    try:
        # Use Message API format
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
            "temperature": 0.1
        })
        
        response = await asyncio.to_thread(
            lambda: bedrock_runtime.invoke_model(
                modelId=PRIMARY_MODEL,
                contentType="application/json",
                accept="application/json",
                body=body
            )
        )
        
        response_body = json.loads(response.get('body').read())
        return response_body.get('content', [{}])[0].get('text', "Error: No response from Claude")
    except Exception as e:
        print(f"❌ [BEDROCK] Claude error: {e}")
        raise

@mcp.tool()
async def generate_twin_response(
    query: str, 
    tenantId: str, 
    system_prompt: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    plan: Optional[str] = "basic"  # "basic" or "premium"
) -> str:
    """Full Advanced RAG Pipeline (Bedrock Edition)"""
    try:
        # 0. Fetch Tenant Metadata
        metadata = await get_tenant_metadata(tenantId)
        actual_plan = metadata.get("plan", plan if plan else "basic")
        tenant_keywords = metadata.get("guardrailKeywords", [])

        # ── Basic Plan: Off-topic Guardrail ──
        if actual_plan == "basic" and is_off_topic(query, tenant_keywords):
            print(f"🚫 [GUARDRAIL] Basic plan blocked off-topic query: '{query[:60]}'")
            return BASIC_GUARDRAIL_RESPONSE

        # ── Per-plan limits ──
        # In Bedrock mode, we always use Rewrite/Rerank for premium, simple flow for basic
        rag_limit   = 5    if actual_plan == "basic" else 15
        max_tokens  = 512  if actual_plan == "basic" else 2048
        history_len = 3    if actual_plan == "basic" else 5

        # 1. Check Semantic Cache
        cached_answer = await get_semantic_cache(query, tenantId, personaId)
        if cached_answer:
            return f"{cached_answer}\n\n(Source: Semantic Cache 🚀)"

        # 2. Advanced RAG Flow
        search_query = query
        if actual_plan == "premium":
            # 2a. Query Rewrite (Mistral)
            search_query = await rewrite_query(query)

        # 2b. Search (returns Top 15 raw hits for premium, 5 for basic)
        raw_hits = await search_knowledge_base(search_query, tenantId, personaId=personaId, limit=rag_limit, return_raw=True)
        
        final_hits = raw_hits
        if actual_plan == "premium" and len(raw_hits) > 3:
            # 2c. Rerank (Cohere) - pick top 5
            final_hits = await rerank_results(query, raw_hits, top_n=5)
            
        # Format context block
        if not final_hits:
            rag_context_block = "Note: No specific records found in the knowledge base for this query."
        else:
            formatted_blocks = []
            for res in final_hits:
                src = res.payload.get("filename", "Unknown")
                txt = res.payload.get("text", "")
                formatted_blocks.append(f"DOCUMENT: {src}\nCONTENT: {txt}\n---")
            rag_context_block = "\n".join(formatted_blocks)

        # 3. LLM Generation
        llm_messages = []
        if messages:
            for msg in messages[-history_len:]:
                if msg.get("content"):
                    llm_messages.append({"role": msg.get("role", "user"), "content": msg.get("content")})
        
        persona_label = personaId if personaId else "Digital Brain"
        rag_prompt = f"""Role: You are the Digital Brain ([Persona: {persona_label}]). 

Retrieved Wisdom:
{rag_context_block}

Current Discussion:
{query}

Rules:
1. Speak in first person ("I", "We", "Our")
2. Use Retrieved Wisdom precisely
3. Cite sources using (Ref: filename.ext)
4. If no data: "Based on my records, I don't have those details..."
"""
        llm_messages.append({"role": "user", "content": rag_prompt})

        # ── LLM Invocation ──
        if LLM_PROVIDER == "bedrock":
            print(f"📡 Routing to Bedrock: {PRIMARY_MODEL}")
            answer = await call_bedrock_claude(system_prompt, llm_messages, max_tokens)
        else:
            print(f"📡 Routing to OpenAI fallback")
            response = await asyncio.to_thread(
                lambda: openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system_prompt}] + llm_messages,
                    temperature=0.1
                )
            )
            answer = response.choices[0].message.content

        # 4. Save to Cache
        negative_triggers = ["don't have those details", "no specific records found", "don't have information"]
        if not any(t in answer.lower() for t in negative_triggers):
            await save_to_semantic_cache(query, answer, tenantId, personaId)
        
        return answer

    except Exception as e:
        print(f"❌ RAG Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"MCP Error: {str(e)}"

@mcp.tool()
async def clear_tenant_knowledge(tenantId: str) -> str:
    """Wipe all knowledge for a specific tenant (all personas)."""
    try:
        tenantId = tenantId.strip().lower()
        prefix = tenantId.replace("-", "_")
        
        # Get all collections
        collections_response = qdrant.get_collections()
        deleted_count = 0
        
        for col in collections_response.collections:
            name = col.name
            if name == prefix or name.startswith(f"{prefix}_"):
                print(f"🗑 Deleting collection: {name}")
                qdrant.delete_collection(name)
                deleted_count += 1
        
        # Also clear cache
        await clear_semantic_cache_for_tenant(tenantId)
        
        return f"Successfully wiped {deleted_count} collections and cache for tenant: {tenantId}"
    except Exception as e:
        return f"Wipe Error: {str(e)}"

@mcp.tool()
async def ingest_knowledge(text: Optional[str] = None, tenantId: str = "", metadata: Optional[dict] = None, **kwargs) -> str:
    """Ingest knowledge from text or S3 (Excel/CSV/Text)."""
    try:
        # 1. Handle S3 source if provided
        s3_bucket = kwargs.get("s3_bucket")
        s3_key = kwargs.get("s3_key")
        
        if s3_bucket and s3_key:
            print(f"📥 [INGEST] Fetching from S3: s3://{s3_bucket}/{s3_key}")
            try:
                s3_client = boto3.client('s3', region_name=AWS_REGION)
                response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
                file_content = response['Body'].read()
                print(f"✅ [INGEST] S3 fetch OK — {len(file_content):,} bytes")
                
                # Detect file type and parse
                ext = s3_key.split('.')[-1].lower()
                print(f"📂 [INGEST] Detected extension: {ext}")
                if ext in ['xlsx', 'xls']:
                    print(f"📊 Parsing Excel with Multi-Sheet Isolation...")
                    xl = pd.ExcelFile(io.BytesIO(file_content))
                    total_successful_chunks = 0
                    
                    for sheet_name in xl.sheet_names:
                        df = pd.read_excel(xl, sheet_name=sheet_name)
                        df = df.dropna(how='all').dropna(axis=1, how='all')
                        if not df.empty:
                            sheet_text = f"SHEET: {sheet_name}\n{df.to_csv(index=False, sep='|')}"
                            
                            # Update metadata for this specific sheet
                            sheet_metadata = {**(metadata or {}), "sheet_name": sheet_name}
                            
                            # Recursive call or inline ingestion for this sheet
                            sheet_res = await ingest_knowledge(
                                text=sheet_text, 
                                tenantId=tenantId, 
                                metadata=sheet_metadata
                            )
                            print(f"  - Sheet '{sheet_name}' result: {sheet_res}")
                    
                    return f"Successfully ingested multi-sheet Excel: {s3_key}"
                elif ext == 'csv':
                    print(f"📄 Parsing CSV...")
                    df = pd.read_csv(io.BytesIO(file_content))
                    text = df.to_csv(index=False, sep='|')
                elif ext == 'docx':
                    print(f"📝 Parsing Word Document...")
                    doc = docx.Document(io.BytesIO(file_content))
                    
                    # Extract from paragraphs
                    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
                    
                    # Extract from tables
                    table_text = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_data = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                            if row_data:
                                table_text.append(" | ".join(row_data))
                    
                    text = "\n".join(paragraphs + table_text)
                elif ext == 'pdf':
                    print(f"📄 [INGEST] Parsing PDF — {len(file_content):,} bytes")
                    pdf_pages = []
                    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                        for page_num, page in enumerate(pdf.pages, start=1):
                            page_text = page.extract_text()
                            if page_text and page_text.strip():
                                pdf_pages.append(f"PAGE {page_num}:\n{page_text.strip()}")
                    print(f"✅ [INGEST] PDF parsed: {len(pdf_pages)} pages with text")
                    if not pdf_pages:
                        return "Error: No extractable text found in PDF"
                    text = "\n\n".join(pdf_pages)
                elif ext == 'pptx':
                    print(f"📊 [INGEST] Parsing PPTX — {len(file_content):,} bytes")
                    prs = PptxPresentation(io.BytesIO(file_content))
                    slide_texts = []
                    for slide_num, slide in enumerate(prs.slides, start=1):
                        slide_content = []
                        for shape in slide.shapes:
                            if hasattr(shape, 'text') and shape.text.strip():
                                slide_content.append(shape.text.strip())
                        if slide_content:
                            slide_texts.append(f"SLIDE {slide_num}:\n" + "\n".join(slide_content))
                    print(f"✅ [INGEST] PPTX parsed: {len(slide_texts)} slides with text")
                    if not slide_texts:
                        return "Error: No extractable text found in PowerPoint"
                    text = "\n\n".join(slide_texts)
                elif ext == 'ppt':
                    return "Error: Old binary .ppt format is not supported. Please save the file as .pptx (PowerPoint 2007+) and re-upload."
                else:
                    # Treat as text
                    text = file_content.decode('utf-8', errors='ignore')
            except Exception as s3_err:
                return f"S3 Error: {str(s3_err)}"

        if not text or not text.strip():
            return "Error: Text content is empty after parsing"
        
        # Ensure metadata is a dict and capture top-level filename info
        if metadata is None:
            metadata = {}
        
        # Capture filename if passed at top level (common in n8n/webhooks)
        fname = kwargs.get("fileName") or kwargs.get("filename") or metadata.get("fileName") or metadata.get("filename")
        if fname:
            metadata["filename"] = fname
            print(f"📎 Found filename in request: {fname}")

        tenantId = tenantId.strip().lower()
        
        # ✅ PERSONA-BASED COLLECTION: Extract persona for naming
        persona_raw = metadata.get("personaId") if metadata else "global"
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any']
        active_persona = str(persona_raw).strip().lower() if (persona_raw and str(persona_raw).strip().lower() not in ignored_personas) else "global"
        
        collection_name = f"{tenantId.replace('-', '_')}_{active_persona}"
        
        print(f"📝 [INGEST] Ingesting for {tenantId} | Persona: {active_persona} | Collection: {collection_name} | Text: {len(text):,} chars")

        chunks = chunk_text(text, chunk_size=2000, overlap=300)
        print(f"🔪 [INGEST] Split into {len(chunks)} chunks — starting embedding...")

        try:
            first_vector = await get_embedding(chunks[0])
        except Exception as emb_err:
            print(f"❌ [INGEST] Embedding FAILED: {emb_err}")
            return f"Error: Embedding failed — {str(emb_err)}"
        vector_size = len(first_vector)
        ensure_collection(collection_name, vector_size)
        
        successful_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                vector = await get_embedding(chunk)
                
                chunk_metadata = {
                    **(metadata or {}),
                    "text": chunk,
                    "tenantId": tenantId.lower(),
                    "personaId": active_persona,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "full_text_hash": get_text_hash(text)[:16]
                }
                
                # ✅ DETERMINISTIC ID: Use hash of content + tenantId to prevent duplicates
                id_seed = f"{tenantId.lower()}:{chunk}".encode()
                point_id = hashlib.sha256(id_seed).hexdigest()[:32]
                
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
        
        # ✅ CACHE INVALIDATION: Clear cache after adding new knowledge
        await clear_semantic_cache_for_tenant(tenantId)
        
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
        "service": "Peak AI 1.0 MCP",
        "version": "3.2-fixed",
        "provider": EMBEDDING_PROVIDER
    })

@app.get("/health")
async def health():
    redis_up = False
    try:
        redis_up = redis_client.ping()
    except:
        pass
    return JSONResponse({"status": "healthy", "redis": redis_up})

@app.get("/stats")
async def stats():
    return JSONResponse({
        "cost_tracker": cost_tracker,
        "cache_debug": cache_debug_log,
        "cache_size": len(embedding_cache),
        "estimated_cost": {
            "embeddings": round(cost_tracker["embedding_calls"] * 0.00002, 4),
            "chat": round(cost_tracker["total_tokens"] * (0.0002 / 1000), 4),
            "total": round((cost_tracker["embedding_calls"] * 0.00002) + (cost_tracker["total_tokens"] * (0.0002 / 1000)), 4)
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
        elif tool_name == "clear_semantic_cache":
            result = await clear_semantic_cache_for_tenant(**arguments)
        elif tool_name == "clear_tenant_knowledge":
            result = await clear_tenant_knowledge(**arguments)
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
║       Peak AI 1.0 MCP Server v3.2-FIXED                      ║
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