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

# Lazy-loaded embedding clients
voyage_client = None
cohere_client = None

# OpenAI Client
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
        
        ignored_personas = ['any', 'global', 'optional', 'none', 'all', 'default', 'global/any', 'user']
        persona_raw = str(personaId).strip().lower() if personaId else None
        active_persona = persona_raw if (persona_raw and persona_raw not in ignored_personas) else "global"
        
        # ✅ PERSONA-BASED COLLECTION: tenant_id + persona_id
        collection_name = f"{tenantId.replace('-', '_')}_{active_persona}"
        
        search_query = query
        if len(query.split()) <= 4:
            search_query = f"The {query} and key metrics or performance data"

        print(f"🔍 [SEARCH] Collection: {collection_name} | Persona: {active_persona} | Query: '{search_query[:50]}...'")
        
        vector = await get_embedding(search_query)

        # 4. Build Filter (STRICT ISOLATION)
        # Even with persona collections, we keep the filter for double-safety
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="personaId",
                    match=models.MatchValue(value=active_persona.lower())
                )
            ]
        )

        # ✅ HIGH-COMPATIBILITY SEARCH: Using robust helper
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
            
            # ✅ ROBUST SOURCE DETECTION: Handle different casing/keys
            source = res.payload.get("filename") or res.payload.get("fileName") or res.payload.get("source") or "Unknown Document"
            sheet = res.payload.get("sheet_name")
            
            hit_persona = res.payload.get("personaId", "None")
            score = getattr(res, 'score', 0)
            
            # Diagnostic print
            print(f"  - Hit #{i+1}: {source} {'['+sheet+']' if sheet else ''} [Score: {score:.4f}] [Tag: {hit_persona}]")
            
            citation = f"DOCUMENT: {source}"
            if sheet:
                citation += f" [SHEET: {sheet}]"
            
            formatted_results.append(f"{citation} (Persona: {hit_persona})\nCONTENT: {text}\n---")

        if not formatted_results and active_persona != "global":
            print(f"⚠ [SEARCH] No results in '{collection_name}'. Falling back to global.")
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
                for i, res in enumerate(search_result):
                    text = res.payload.get("text", "No text found")
                    source = res.payload.get("filename") or res.payload.get("fileName") or res.payload.get("source") or "Global Document"
                    formatted_results.append(f"DOCUMENT: {source} (Global)\nCONTENT: {text}\n---")

        if not formatted_results:
            print(f"⚠ [SEARCH] Zero results found in all target collections")
            return ""

        return "\n\n".join(formatted_results)
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

@mcp.tool()
async def generate_twin_response(
    query: str, 
    tenantId: str, 
    system_prompt: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    plan: Optional[str] = "basic"  # "basic" or "premium"
) -> str:
    """Full RAG Pipeline"""
    try:
        # 0. Fetch Tenant Metadata (including plan and keywords)
        metadata = await get_tenant_metadata(tenantId)
        
        # Override plan if set in metadata
        actual_plan = metadata.get("plan", plan if plan else "basic")
        tenant_keywords = metadata.get("guardrailKeywords", [])

        # ── Basic Plan: Off-topic Guardrail (zero LLM cost) ──
        if actual_plan == "basic" and is_off_topic(query, tenant_keywords):
            print(f"🚫 [GUARDRAIL] Basic plan blocked off-topic query: '{query[:60]}'")
            return BASIC_GUARDRAIL_RESPONSE

        # ── Per-plan limits ──
        rag_limit   = 3    if actual_plan == "basic" else 10
        max_tokens  = 512  if actual_plan == "basic" else 2048
        history_len = 3    if actual_plan == "basic" else 5
        # 1. Check Semantic Cache
        cached_answer = await get_semantic_cache(query, tenantId, personaId)
        if cached_answer:
            return f"{cached_answer}\n\n(Source: Semantic Cache 🚀)"

        context = await search_knowledge_base(query, tenantId, personaId=personaId, limit=rag_limit)
        
        if openai_client is None:
            return "MCP Error: OpenAI API client not initialized."

        print(f"Routing to OpenAI GPT-4o-mini")
        
        if context.startswith("SEARCH_ERROR"):
            # Don't pass technical details to the AI
            rag_context_block = "Note: A temporary search error occurred. Please answer using your general knowledge but mention that specific records are currently unavailable."
        elif not context:
            rag_context_block = "Note: No specific records found in the knowledge base for this query."
        else:
            rag_context_block = context

        openai_messages = [{"role": "system", "content": system_prompt}]
        
        if messages:
            for msg in messages[-history_len:]:
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
3. Cite sources using the exact name after 'DOCUMENT:', e.g.: (Ref: filename.txt)
4. If no data: "Based on my records, I don't have those details..."
5. Format data with tables/bullets
"""
        
        openai_messages.append({"role": "user", "content": rag_prompt})

        for attempt in range(2):
            try:
                response = await asyncio.to_thread(
                    lambda: openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        max_tokens=max_tokens,
                        messages=openai_messages,
                        temperature=0.1
                    )
                )
                answer = response.choices[0].message.content
                
                if response.usage:
                    cost_tracker["total_tokens"] += response.usage.total_tokens
                    cost_tracker["chat_calls"] += 1
                
                
                # 4. Save to Cache ONLY if we found actual data
                # Don't cache "I don't have those details" to allow for future knowledge updates
                negative_triggers = ["don't have those details", "no specific records found", "don't have information"]
                is_negative = any(trigger in answer.lower() for trigger in negative_triggers)
                
                if not is_negative:
                    await save_to_semantic_cache(query, answer, tenantId, personaId)
                else:
                    print("ℹ Skipping cache save for 'No Data' response.")
                
                return answer
            except Exception as e:
                if attempt == 1: raise
                print(f"⚠ Retry after error: {str(e)}")
                await asyncio.sleep(1)

    except Exception as e:
        print(f"✗ OpenAI error: {str(e)}")
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
                s3_client = boto3.client('s3')
                response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
                file_content = response['Body'].read()
                
                # Detect file type and parse
                ext = s3_key.split('.')[-1].lower()
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
        
        print(f"Ingesting for {tenantId} | Persona: {active_persona} | Collection: {collection_name} ({len(text)} chars)")
        
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