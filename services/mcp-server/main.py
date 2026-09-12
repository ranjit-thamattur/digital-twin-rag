import os
import asyncio
import json
import time
import uuid
import hashlib
from typing import Optional, List, Any
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
from prompts import ACTIVE_SYSTEM_PROMPT, RAG_GENERATION_PROMPT, CHIEF_OF_STAFF_SYSTEM_PROMPT

# Bedrock Embeddings
# Removed local torch imports to save memory

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "172.17.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
REDIS_HOST = os.getenv("REDIS_HOST", "172.17.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "bedrock")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "amazon.nova-pro-v1:0")
REWRITE_MODEL = os.getenv("REWRITE_MODEL", "mistral.ministral-3-14b-instruct")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cohere.rerank-v3-5:0")

# API Keys for embedding providers
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Feature Flags
# Set CHIEF_OF_STAFF_ENABLED=true in .env to activate Phase 2 Chief of Staff routing.
# Defaults to false so Phase 1 ships without it.
CHIEF_OF_STAFF_ENABLED = os.getenv("CHIEF_OF_STAFF_ENABLED", "false").lower() == "true"

# Vector sizes by provider
VECTOR_SIZES = {
    "titan": 1024,  # amazon.titan-embed-text-v2:0
    "local": 768,   # all-mpnet-base-v2
    "voyage": 1024,
    "openai": 1536,
    "cohere": 1024
}
VECTOR_SIZE = VECTOR_SIZES.get(EMBEDDING_PROVIDER, 768)

# Initialize FastMCP server
mcp = FastMCP("Peak AI 1.0 Knowledge Base")
VERSION = "3.8-TYPE-SAFE"
print(f"🚀 Starting Peak AI MCP Server {VERSION}")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant = qdrant_client.QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT,
    timeout=30,
    prefer_grpc=False
)

# Bedrock Client
bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)

# Lazy-loaded embedding models
voyage_client = None
cohere_client = None
# local_embed_model removed

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
    redis_client.ping()
    print("✅ Redis connection successful")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")

# DynamoDB Configuration
TENANT_TABLE = os.getenv("TENANT_TABLE", "clonemind-tenants")
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
# CHIEF OF STAFF AI — WORKFLOW TEMPLATES
# Keyword-based matching. No LLM involved in routing.
# Add / remove workflows here to configure org event detection.
# ─────────────────────────────────────────────

WORKFLOW_TEMPLATES = {
    "HIRE_EVENT": {
        "triggers": ["hired", "joining", "new hire", "onboard", "recruited",
                     "appointed", "we hired", "just hired", "new employee",
                     "new team member", "new staff"],
        "roles":   ["hr", "finance", "sales", "admin", "coach"],
        "label":   "New Hire Coordination",
        "icon":    "👤"
    },
    "CLIENT_SIGNED": {
        "triggers": ["signed", "new client", "contract signed", "deal closed",
                     "onboarded client", "client onboard", "new customer",
                     "client signed", "deal signed"],
        "roles":   ["sales", "finance", "admin", "coach"],
        "label":   "New Client Onboarding",
        "icon":    "🤝"
    },
    "BUDGET_APPROVED": {
        "triggers": ["budget approved", "budget allocated", "funds approved",
                     "approved the budget", "budget confirmed", "funding approved"],
        "roles":   ["finance", "admin"],
        "label":   "Budget Approval Coordination",
        "icon":    "💰"
    },
    "PRODUCT_LAUNCH": {
        "triggers": ["launching", "going live", "new product", "new feature",
                     "release date", "we are launching", "product launch",
                     "releasing", "ship the", "shipping"],
        "roles":   ["sales", "finance", "admin"],
        "label":   "Product Launch Coordination",
        "icon":    "🚀"
    },
    "TEAM_CHANGE": {
        "triggers": ["promoted", "restructure", "reporting to", "new role",
                     "transferred", "team change", "role change", "promotion",
                     "new manager", "org change"],
        "roles":   ["hr", "finance", "admin"],
        "label":   "Team Change Coordination",
        "icon":    "🔄"
    }
}

ROLE_ICONS = {
    "hr":      "📋 HR",
    "finance": "💰 Finance",
    "sales":   "🎯 Sales",
    "admin":   "🔑 Admin",
    "coach":   "📅 AI Coach"
}


def match_workflow(query: str) -> Optional[dict]:
    """Pure keyword-based workflow matcher — no LLM, no guessing.
    Returns the first matching workflow template dict, or None."""
    q = query.lower()
    for workflow_id, template in WORKFLOW_TEMPLATES.items():
        if any(trigger in q for trigger in template["triggers"]):
            return {"workflow_id": workflow_id, **template}
    return None


def format_chief_output(matched: dict, roles: list, responses: list) -> dict:
    """Formats multi-role responses as labelled sections.
    NEVER merges or synthesizes across roles."""
    lines = [f"**Chief of Staff coordinated: {matched['label']}**\n"]
    for role, response in zip(roles, responses):
        icon = ROLE_ICONS.get(role, role.upper())
        if isinstance(response, Exception):
            lines.append(f"{icon}\nUnable to retrieve — {str(response)}\n")
        else:
            if isinstance(response, dict):
                answer = response.get("answer", "No documented process found for this event.")
            else:
                answer = str(response) if response else "No documented process found for this event."
            lines.append(f"{icon}\n{answer}\n")
    return {
        "answer": "\n---\n".join(lines),
        "type": "chief_response",
        "roles_involved": roles
    }

# ─────────────────────────────────────────────
# COLLECTION NAME NORMALIZATION — single source of truth
# ─────────────────────────────────────────────

IGNORED_PERSONAS = {'any', 'global', 'optional', 'none', 'all', 'default', 'global/any', 'user'}


def normalize_tenant_id(tenantId: str) -> str:
    """Return a clean, prefixed tenant slug for use in collection names.
    
    Always produces: tenant_{slug}
    Examples:
      "My-Company"  -> "tenant_my_company"
      "tenant-abc"  -> "tenant_abc"          (de-duplicates the prefix)
      "tenant_abc"  -> "tenant_abc"
    """
    t = tenantId.strip().lower().replace('-', '_')
    # Strip an existing "tenant_" prefix before re-adding so we never get
    # "tenant_tenant_abc" from a tenantId that already starts with "tenant-".
    if t.startswith("tenant_"):
        t = t[len("tenant_"):]
    return f"tenant_{t}"


def normalize_persona(personaId) -> str:
    """Return a clean persona slug, falling back to 'global' for ignored values."""
    p = str(personaId).strip().lower() if personaId else "global"
    return p if p not in IGNORED_PERSONAS else "global"


def normalize_collection_name(tenantId: str, personaId=None, suffix: str = "") -> str:
    """Single source of truth for Qdrant collection names.

    Format: tenant_{id}_{persona}[_{suffix}]

    Examples:
      normalize_collection_name("my-company", "CEO")        -> "tenant_my_company_ceo"
      normalize_collection_name("my-company", "global")     -> "tenant_my_company_global"
      normalize_collection_name("my-company", "ceo", "cache") -> "tenant_my_company_ceo_cache"
      normalize_collection_name("tenant-abc", "ceo")        -> "tenant_abc_ceo"
    """
    t = normalize_tenant_id(tenantId)
    p = normalize_persona(personaId)
    name = f"{t}_{p}"
    if suffix:
        name = f"{name}_{suffix}"
    return name


# ─────────────────────────────────────────────
# BASIC PLAN: Off-topic / Casual Chat Guardrail
# ─────────────────────────────────────────────
OFF_TOPIC_PATTERNS = [
    "tell me a joke", "write a poem", "write a story", "what is 2+2",
    "who is your favourite", "what's the weather", "weather today",
    "hello there", "what can you do", "write an email to my friend",
    "translate this", "play a game", "what are your hobbies",
    "do you like", "can you sing",
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
    "That's outside what my knowledge base covers. Ask me something "
    "related to your company, strategy, clients, or documents "
    "and I'll give you a precise answer."
)


def is_off_topic(query: str, tenant_keywords: Optional[List[str]] = None) -> bool:
    """Returns True if the query is casual/off-topic for a Basic plan tenant."""
    q = query.lower().strip()

    # Always allow session-opening greetings — they route to the LLM for persona intro
    GREETING_PASSTHROUGH = {"hello", "hi", "hey", "hola", "howdy", "greetings", "good morning",
                            "good afternoon", "good evening", "sup", "yo"}
    if q in GREETING_PASSTHROUGH or any(q.startswith(g) for g in GREETING_PASSTHROUGH):
        return False

    all_business_keywords = BUSINESS_KEYWORDS
    if tenant_keywords:
        all_business_keywords = list(set(BUSINESS_KEYWORDS + [k.lower() for k in tenant_keywords]))

    if any(p in q for p in OFF_TOPIC_PATTERNS):
        return True
    return False


async def get_tenant_metadata(tenantId: str) -> dict:
    """Retrieves metadata for a tenant from Redis cache or DynamoDB."""
    cache_key = f"tenant:{tenantId}:metadata"

    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        print(f"⚠ Redis cache fetch failed for metadata: {e}")

    try:
        response = await asyncio.to_thread(
            lambda: tenant_metadata_table.get_item(Key={'tenantId': tenantId})
        )
        metadata = response.get('Item', {})

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
# EMBEDDING HELPERS
# ─────────────────────────────────────────────

def get_text_hash(text: str) -> str:
    """Create a hash of the text for caching."""
    return hashlib.sha256(text.encode()).hexdigest()


async def get_titan_embedding(text: str) -> List[float]:
    """Generate embedding using Amazon Bedrock Titan Embeddings V2."""
    import json
    body = json.dumps({
        "inputText": text,
        "dimensions": 1024,
        "normalize": True
    })
    
    result = await asyncio.to_thread(
        lambda: bedrock_runtime.invoke_model(
            body=body,
            modelId="amazon.titan-embed-text-v2:0",
            accept="application/json",
            contentType="application/json"
        )
    )
    
    response_body = json.loads(result.get('body').read())
    return response_body.get('embedding')


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
            if attempt == 2:
                raise
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
        elif EMBEDDING_PROVIDER == "titan":
            embedding = await get_titan_embedding(text)
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


def robust_qdrant_search(collection_name: str, vector: list, limit: int = 1,
                          score_threshold: float = None, query_filter: Any = None):
    """Helper to perform search across different Qdrant client versions."""
    try:
        if hasattr(qdrant, 'search'):
            return qdrant.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True
            )
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


# ─────────────────────────────────────────────
# SEMANTIC CACHE
# ─────────────────────────────────────────────

import re
def detect_query_language(text: str) -> str:
    if re.search(r'[\u0D00-\u0D7F]', text): return 'ml'
    if re.search(r'[\u0B80-\u0BFF]', text): return 'ta'
    if re.search(r'[\u0900-\u097F]', text): return 'hi'
    return 'en'

async def get_semantic_cache(query: str, tenantId: str, personaId: Optional[str] = None) -> Optional[str]:
    """Check if a semantically similar question exists in the persona-specific cache."""
    if os.getenv("DISABLE_SEMANTIC_CACHE", "false").lower() == "true":
        return None

    try:
        tenantId = tenantId.strip().lower()
        clean_query = query.strip().strip('*').strip('_').strip()
        if not clean_query:
            clean_query = query

        cache_collection = normalize_collection_name(tenantId, personaId, suffix="cache")

        vector = await get_embedding(clean_query)
        ensure_collection(cache_collection, len(vector))

        query_lang = detect_query_language(clean_query)
        
        # Build language filter
        lang_filter = models.Filter(must=[
            models.FieldCondition(
                key="lang",
                match=models.MatchValue(value=query_lang)
            )
        ])

        results = await asyncio.to_thread(
            robust_qdrant_search,
            collection_name=cache_collection,
            vector=vector,
            limit=1,
            score_threshold=0.99,
            query_filter=lang_filter
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
        if len(cache_debug_log) > 20:
            cache_debug_log.pop(0)
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
        # FIX: use normalize_collection_name — single source of truth
        tenantId = tenantId.strip().lower()
        clean_query = query.strip().strip('*').strip('_').strip()
        if not clean_query:
            clean_query = query

        cache_collection = normalize_collection_name(tenantId, personaId, suffix="cache")

        vector = await get_embedding(clean_query)
        ensure_collection(cache_collection, len(vector))

        cache_id = str(uuid.uuid4())

        # Derive active_persona for payload storage
        active_persona = normalize_persona(personaId)

        payload = {
            "query": query,
            "tenantId": tenantId.lower(),
            "personaId": active_persona,
            "lang": detect_query_language(clean_query),
            "cache_id": cache_id,
            "created_at": time.time()
        }

        qdrant.upsert(
            collection_name=cache_collection,
            points=[models.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload)]
        )

        redis_client.setex(f"cache:{cache_id}", 86400, answer)
        print(f"💾 [CACHE SAVE] Collection: {cache_collection}")
    except Exception as e:
        print(f"⚠ Cache save error: {str(e)}")


async def clear_semantic_cache_for_tenant(tenantId: str):
    """Wipe all semantic cache collections for a specific tenant."""
    try:
        # FIX: normalize_tenant_id guarantees the "tenant_" prefix is present
        # so the startswith check correctly matches all tenant collections
        prefix = normalize_tenant_id(tenantId.strip().lower())

        collections_response = qdrant.get_collections()
        deleted_count = 0

        for col in collections_response.collections:
            name = col.name
            if name.startswith(f"{prefix}_") and name.endswith("_cache"):
                print(f"🧹 Deleting cache collection: {name}")
                qdrant.delete_collection(name)
                deleted_count += 1

        embedding_cache.clear()
        print("🧼 Flushing in-memory vector cache")

        return True
    except Exception as e:
        print(f"⚠ Cache clear error: {str(e)}")
        return False


# ─────────────────────────────────────────────
# MCP TOOLS
# ─────────────────────────────────────────────

@mcp.tool()
async def search_knowledge_base(
    query: str,
    tenantId: str = "",
    limit: int = 5,
    personaId: str = "ceo",
    filename: Optional[str] = None,
    return_raw: bool = False
) -> Any:
    """Search the knowledge base for a specific tenant and persona.
    Use 'filename' to restrict search to a specific document."""
    if not tenantId or not query or not query.strip():
        return "Please provide both tenantId and a search query."

    try:
        # FIX: normalize via shared helpers — no inline normalization
        tenantId = tenantId.strip().lower()
        active_persona = normalize_persona(personaId)
        collection_name = normalize_collection_name(tenantId, active_persona)

        # Handle contextual references
        context_words = ["this sheet", "this document", "that sheet", "the file", "the sheet", "it"]
        is_contextual = any(word in query.lower() for word in context_words)

        search_query = query
        if len(query.split()) <= 4:
            search_query = f"The {query} and key metrics or performance data"

        print(f"🔍 [SEARCH] Collection: {collection_name} | Persona: {active_persona} | "
              f"Filename Filter: {filename} | Query: '{search_query[:50]}...'")

        vector = await get_embedding(search_query)

        # Build filter (strict isolation by collection, but allow specific persona + common)
        must_filters = [
            models.FieldCondition(
                key="personaId",
                match=models.MatchAny(any=[active_persona, "common"])
            )
        ]

        if filename:
            must_filters.append(
                models.FieldCondition(
                    key="filename",
                    match=models.MatchValue(value=filename)
                )
            )

        query_filter = models.Filter(must=must_filters)

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
            source = (res.payload.get("filename") or res.payload.get("fileName")
                      or res.payload.get("source") or "Unknown Document")
            sheet = res.payload.get("sheet_name")
            hit_persona = res.payload.get("personaId", "None")
            score = getattr(res, 'score', 0)

            print(f"  - Hit #{i+1}: {source} {'['+sheet+']' if sheet else ''} [Score: {score:.4f}]")

            citation = f"DOCUMENT: {source}"
            if sheet:
                citation += f" [SHEET: {sheet}]"

            formatted_results.append(f"{citation} (Persona: {hit_persona})\nCONTENT: {text}\n---")



        if return_raw:
            return search_result

        if not formatted_results:
            return ""

        return "\n".join(formatted_results)

    except Exception as e:
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
        prompt = (
            "Rewrite this search query to be more descriptive and optimized for a "
            f"vector search engine. Only return the rewritten query text: {original_query}"
        )

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


async def rerank_results(query: str, hits: List[Any], top_n: int = 5) -> List[Any]:
    """Use Cohere Rerank on Bedrock to pick the most relevant chunks."""
    if not hits:
        return []
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
    """Invoke any Bedrock model using the unified Converse API."""
    try:
        formatted_messages = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                content = [{"text": content}]
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": content
            })

        # Converse API requirement: first message must be 'user'
        while formatted_messages and formatted_messages[0]["role"] != "user":
            print(f"🧹 [BEDROCK] Removing leading {formatted_messages[0]['role']} message")
            formatted_messages.pop(0)

        if not formatted_messages:
            return "Error: No user messages found in conversation history."

        print(f"📡 Routing to Bedrock (Converse): {PRIMARY_MODEL}")
        response = await asyncio.to_thread(
            lambda: bedrock_runtime.converse(
                modelId=PRIMARY_MODEL,
                messages=formatted_messages,
                system=[{"text": system_prompt}] if system_prompt else [],
                inferenceConfig={
                    "maxTokens": max_tokens,
                    "temperature": 0.1,
                    "topP": 0.9
                }
            )
        )

        return response['output']['message']['content'][0]['text']
    except Exception as e:
        print(f"❌ [BEDROCK] error: {e}")
        raise


@mcp.tool()
async def generate_twin_response(
    query: str,
    tenantId: str,
    system_prompt: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    plan: Optional[str] = "basic"
) -> Any:
    """Full Advanced RAG Pipeline (Bedrock Edition)"""
    try:
        # 0. Fetch Tenant Metadata
        metadata = await get_tenant_metadata(tenantId)
        actual_plan = metadata.get("plan", plan if plan else "basic")
        tenant_keywords = metadata.get("guardrailKeywords", [])

        # Validate persona against tenant's allowed personas (generic multi-persona support)
        # DynamoDB fields: allowedPersonas (list), defaultPersona (string)
        allowed_personas = metadata.get("allowedPersonas", [])
        default_persona  = metadata.get("defaultPersona", "ceo")
        if allowed_personas and personaId not in allowed_personas:
            print(f"🎭 [RAG] Persona '{personaId}' not in allowedPersonas {allowed_personas} → using '{default_persona}'")
            personaId = default_persona

        # Basic Plan: off-topic guardrail
        if actual_plan == "basic" and is_off_topic(query, tenant_keywords):
            print(f"🚫 [GUARDRAIL] Basic plan blocked off-topic query: '{query[:60]}'")
            return BASIC_GUARDRAIL_RESPONSE

        # Cache Clear Backdoor
        if query.strip().lower() == "/clear":
            await clear_semantic_cache_for_tenant(tenantId)
            return "Semantic cache has been fully cleared for your tenant. You can now ask questions normally!"

        # Per-plan limits
        rag_limit   = 5    if actual_plan == "basic" else 15
        max_tokens  = 512  if actual_plan == "basic" else 2048
        history_len = 3    if actual_plan == "basic" else 5

        # 1. Check Semantic Cache (Disabled by request)
        # cached_answer = await get_semantic_cache(query, tenantId, personaId)
        # if cached_answer:
        #     return cached_answer

        # 2. Advanced RAG Flow
        search_query = query
        if actual_plan == "premium":
            search_query = await rewrite_query(query)

        # search_knowledge_base normalizes internally via normalize_collection_name
        raw_hits = await search_knowledge_base(
            search_query, tenantId, personaId=personaId, limit=rag_limit, return_raw=True
        )

        final_hits = raw_hits
        if actual_plan == "premium" and len(raw_hits) > 3:
            final_hits = await rerank_results(query, raw_hits, top_n=5)

        # Format context block
        memory_used = []
        if not final_hits:
            rag_context_block = "Note: No specific records found in the knowledge base for this query."
        else:
            formatted_blocks = []
            seen_files = set()
            for idx, res in enumerate(final_hits, start=1):
                src = res.payload.get("filename", "Unknown")
                txt = res.payload.get("text", "")
                formatted_blocks.append(f"RECORD: {src}\n{txt}\n---")
                
                if src not in seen_files:
                    seen_files.add(src)
                    memory_used.append({"id": idx, "filename": src, "snippet": txt[:200] + "..."})
                    
            rag_context_block = "\n".join(formatted_blocks)

        # 3. LLM Generation
        llm_messages = []
        if messages:
            for msg in messages[-history_len:]:
                if msg.get("content"):
                    llm_messages.append({"role": msg.get("role", "user"), "content": msg.get("content")})

        def format_persona_name(pid: Optional[str]) -> str:
            if not pid:
                return "Digital Brain"
            pid_lower = pid.lower().strip()
            if pid_lower == "ceo":
                return "CEO"
            if pid_lower == "cfo":
                return "CFO"
            if pid_lower == "cto":
                return "CTO"
            if pid_lower in ("hr", "hr_manager"):
                return "HR Head"
            return pid.replace("_", " ").title()

        persona_label = format_persona_name(personaId)
        tenant_name = tenantId.replace("tenant-", "") if tenantId else "the organisation"

        # Format system prompt with live persona/tenant context
        system_prompt = ACTIVE_SYSTEM_PROMPT.format(
            persona_label=persona_label,
            tenant_name=tenant_name
        )

        rag_prompt = RAG_GENERATION_PROMPT.format(
            persona_label=persona_label,
            tenant_name=tenant_name,
            rag_context_block=rag_context_block,
            query=query
        )
        llm_messages.append({"role": "user", "content": rag_prompt})

        # LLM Invocation
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

        # 4. Save to Cache (Disabled by request)
        # negative_triggers = ["don't have those details", "no specific records found", "don't have information"]
        # if not any(t in answer.lower() for t in negative_triggers):
        #     await save_to_semantic_cache(query, answer, tenantId, personaId)

        return {"answer": answer, "memory_used": memory_used}

    except Exception as e:
        print(f"❌ RAG Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"MCP Error: {str(e)}"


@mcp.tool()
async def chief_of_staff(
    query: str,
    tenantId: str,
    personaId: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    confirmed: bool = False
) -> Any:
    """Chief of Staff AI — Invisible Router with mandatory confirmation.

    Flow:
      - No workflow match  → route silently to Digital Brain (single role)
      - Workflow match + confirmed=False → return confirmation card (no action)
      - Workflow match + confirmed=True  → fan out to multiple roles in parallel
    """
    try:
        # Feature flag — disabled during Phase 1
        if not CHIEF_OF_STAFF_ENABLED:
            print(f"🔒 [CHIEF] Disabled (Phase 1) — routing directly to Digital Brain (persona={personaId})")
            return await generate_twin_response(
                query=query,
                tenantId=tenantId,
                system_prompt=ACTIVE_SYSTEM_PROMPT,
                personaId=personaId,
                messages=messages
            )

        # STEP 1: keyword match — no LLM involved
        matched = match_workflow(query)

        # STEP 2: No match → route silently to Digital Brain
        if not matched:
            print(f"🧠 [CHIEF] No workflow match — routing to Digital Brain (persona={personaId})")
            return await generate_twin_response(
                query=query,
                tenantId=tenantId,
                system_prompt=ACTIVE_SYSTEM_PROMPT,
                personaId=personaId,
                messages=messages
            )

        # STEP 3: Match found but NOT confirmed → return confirmation card (no execution)
        if not confirmed:
            print(f"🎯 [CHIEF] Workflow match: {matched['workflow_id']} — awaiting confirmation")
            return {
                "type":        "confirmation_required",
                "workflow_id": matched["workflow_id"],
                "label":       matched["label"],
                "icon":        matched["icon"],
                "roles":       matched["roles"],
                "event":       query,
                "message":     f"Organizational event detected: **{matched['label']}**"
            }

        # STEP 4: Confirmed → execute multi-role fan-out in parallel
        roles = matched["roles"]
        print(f"✅ [CHIEF] Confirmed — fanning out to roles: {roles}")

        tasks = [
            generate_twin_response(
                query=query,        # verbatim original — always re-injected fresh
                tenantId=tenantId,
                system_prompt=ACTIVE_SYSTEM_PROMPT,
                personaId=role,
                messages=[]         # clean context per role — no cross-role contamination
            )
            for role in roles
        ]
        role_responses = await asyncio.gather(*tasks, return_exceptions=True)

        result = format_chief_output(matched, roles, role_responses)
        print(f"✅ [CHIEF] Completed coordination for {len(roles)} roles")
        return result

    except Exception as e:
        print(f"❌ [CHIEF] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Chief of Staff Error: {str(e)}"


@mcp.tool()
async def clear_tenant_knowledge(tenantId: str) -> str:
    """Wipe all knowledge for a specific tenant (all personas)."""
    try:
        # FIX: normalize_tenant_id guarantees "tenant_" prefix for correct prefix matching
        prefix = normalize_tenant_id(tenantId.strip().lower())

        collections_response = qdrant.get_collections()
        deleted_count = 0

        for col in collections_response.collections:
            name = col.name
            if name == prefix or name.startswith(f"{prefix}_"):
                print(f"🗑 Deleting collection: {name}")
                qdrant.delete_collection(name)
                deleted_count += 1

        await clear_semantic_cache_for_tenant(tenantId)

        return f"Successfully wiped {deleted_count} collections and cache for tenant: {tenantId}"
    except Exception as e:
        return f"Wipe Error: {str(e)}"


@mcp.tool()
async def ingest_knowledge(
    text: Optional[str] = None,
    tenantId: str = "",
    metadata: Optional[dict] = None,
    **kwargs: Any
) -> str:
    """Ingest knowledge from text or S3 (Excel/CSV/Text/PDF/PPTX/DOCX)."""
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

                ext = s3_key.split('.')[-1].lower()
                print(f"📂 [INGEST] Detected extension: {ext}")

                if ext in ['xlsx', 'xls']:
                    print(f"📊 Parsing Excel with Multi-Sheet Isolation...")
                    xl = pd.ExcelFile(io.BytesIO(file_content))

                    for sheet_name in xl.sheet_names:
                        df = pd.read_excel(xl, sheet_name=sheet_name)
                        df = df.dropna(how='all').dropna(axis=1, how='all')
                        if not df.empty:
                            sheet_text = f"SHEET: {sheet_name}\n{df.to_csv(index=False, sep='|')}"
                            sheet_metadata = {**(metadata or {}), "sheet_name": sheet_name}
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
                    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
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
                    return ("Error: Old binary .ppt format is not supported. "
                            "Please save the file as .pptx (PowerPoint 2007+) and re-upload.")
                else:
                    text = file_content.decode('utf-8', errors='ignore')

            except Exception as s3_err:
                return f"S3 Error: {str(s3_err)}"

        if not text or not text.strip():
            return "Error: Text content is empty after parsing"

        if metadata is None:
            metadata = {}

        # Capture filename if passed at top level
        fname = (kwargs.get("fileName") or kwargs.get("filename")
                 or metadata.get("fileName") or metadata.get("filename"))
        if fname:
            metadata["filename"] = fname
            print(f"📎 Found filename in request: {fname}")

        tenantId = tenantId.strip().lower()

        # FIX: use normalize_collection_name — no inline normalization
        persona_raw = metadata.get("personaId") if metadata else None
        active_persona = normalize_persona(persona_raw)
        collection_name = normalize_collection_name(tenantId, active_persona)

        print(f"📝 [INGEST] Ingesting for {tenantId} | Persona: {active_persona} | "
              f"Collection: {collection_name} | Text: {len(text):,} chars")

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

                # Deterministic ID: hash of content + tenantId prevents duplicates
                id_seed = f"{tenantId.lower()}:{chunk}".encode()
                point_id = hashlib.sha256(id_seed).hexdigest()[:32]

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

        print(f"✓ Ingested {successful_chunks}/{len(chunks)} chunks into '{collection_name}'")

        # Cache invalidation after new knowledge is added
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
Chat Provider: Bedrock / OpenAI fallback

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
    """Clear in-memory embedding cache"""
    cache_size = len(embedding_cache)
    embedding_cache.clear()
    return f"Cleared {cache_size} cached embeddings"


# ─────────────────────────────────────────────
# FastAPI HTTP Bridge
# ─────────────────────────────────────────────

@app.get("/")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "service": "Peak AI 1.0 MCP",
        "version": VERSION,
        "provider": EMBEDDING_PROVIDER
    })


@app.get("/health")
async def health():
    redis_up = False
    try:
        redis_up = redis_client.ping()
    except Exception:
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
            "total": round(
                (cost_tracker["embedding_calls"] * 0.00002)
                + (cost_tracker["total_tokens"] * (0.0002 / 1000)), 4
            )
        }
    })


@app.post("/call/{tool_name}")
async def call_tool_bridge(tool_name: str, request: Request):
    """HTTP bridge for MCP tools"""
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
        elif tool_name == "chief_of_staff":
            result = await chief_of_staff(**arguments)
        else:
            return JSONResponse({"error": f"Tool not found: {tool_name}"}, status_code=404)

        return JSONResponse({"content": result})
    except Exception as e:
        import traceback
        print(f"Error: {traceback.format_exc()}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# OpenAI Compatibility Layer (OpenWebUI Integration)
# ─────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    """Returns a list of available 'Digital Brain' models for OpenWebUI."""
    return JSONResponse({
        "object": "list",
        "data": [
            {
                "id": "digital-brain",
                "object": "model",
                "created": 1700000000,
                "owned_by": "peak-ai",
                "permission": [],
                "root": "digital-brain",
                "parent": None
            }
        ]
    })


@app.post("/v1/chat/completions")
async def openai_chat_bridge(request: Request):
    """Standard OpenAI Chat completions endpoint.
    Converts OpenAI requests to 'generate_twin_response' calls."""
    try:
        body = await request.json()
        headers = dict(request.headers)

        print(f"DEBUG_HEADERS: {json.dumps(headers)}")
        print(f"DEBUG_BODY: {json.dumps(body)}")

        messages = body.get("messages", [])
        if not messages:
            return JSONResponse({"error": "No messages provided"}, status_code=400)

        user_query = messages[-1].get("content", "")

        tenant_id = "default"
        persona_id = "global"

        # 1. Try user info from body (OpenWebUI sends a string in 'user')
        user_field = body.get("user")
        if isinstance(user_field, dict):
            user_email = user_field.get("email")
        elif isinstance(user_field, str):
            user_email = user_field
        else:
            user_email = None
        
        # 2. Try header values (case-insensitive)
        if not user_email:
            user_email = headers.get("x-user-email") or headers.get("X-User-Email") or headers.get("user-email")
        
        header_tenant = headers.get("x-tenant-id") or headers.get("X-Tenant-Id") or headers.get("tenant-id")
        if header_tenant:
            tenant_id = header_tenant.lower()
            print(f"🆔 [BRIDGE] Using tenant from header: {tenant_id}")

        # 3. Authorization-based tenant override
        auth_header = headers.get("authorization", "")
        if "Bearer " in auth_header:
            token = auth_header.replace("Bearer ", "").strip()
            # If token looks like an email, use it
            if "@" in token:
                user_email = token.lower()
            elif token and token != "mcp-bridge":
                print(f"🔑 [BRIDGE] Using tenant from Bearer token: {token}")
                tenant_id = token.lower()

        # 4. Email-based fallback — generic for any tenant
        if tenant_id == "default" and user_email and "@" in user_email:
            local, domain = user_email.split("@", 1)
            domain = domain.lower()
            local  = local.lower().replace(".", "_").replace("-", "_")

            # Tenant ID: normalise domain root
            clean_domain = domain.split(".")[0]
            tenant_id = f"tenant-{clean_domain}"
            # Persona: always derived from email username
            # Validation against allowedPersonas happens inside generate_twin_response
            persona_id = local
            print(f"📧 [BRIDGE] Inferred identity from email: {tenant_id}:{persona_id}")

        # 5. Model suffix override (digital-brain:tenant_id)
        model_name = body.get("model", "digital-brain")
        if ":" in model_name:
            _, suffix = model_name.split(":", 1)
            tenant_id = suffix.strip().lower()
            print(f"🏷 [BRIDGE] Using tenant from model suffix: {tenant_id}")

        # 6. Metadata overrides
        metadata = user_field.get("metadata", {}) if isinstance(user_field, dict) else body.get("metadata", {})
        if metadata:
            tenant_id = metadata.get("tenantId", tenant_id).strip().lower()
            persona_id = metadata.get("personaId", persona_id).strip().lower()

        # 🧠 SMART SESSION RECALL: If still default, check Redis
        session_key = f"session:{headers.get('x-forwarded-for', request.client.host)}:identity"
        if tenant_id == "default":
            cached_identity = redis_client.get(session_key)
            if cached_identity:
                c_tenant, c_persona = cached_identity.split(":")
                tenant_id, persona_id = c_tenant, c_persona
                print(f"🧠 [BRIDGE] SESSION RECALLED: {tenant_id}:{persona_id}")

        # 🎭 PERSONA FALLBACK: last-resort for unresolvable identity
        # Fine-grained validation runs inside generate_twin_response via allowedPersonas
        if tenant_id != "default" and not persona_id:
            persona_id = "ceo"
            print(f"🎭 [BRIDGE] No persona resolved → defaulting to 'ceo'")
        
        # 💾 SESSION SAVE: Remember successful non-default identity
        if tenant_id != "default":
            redis_client.setex(session_key, 3600, f"{tenant_id}:{persona_id}")
            print(f"💾 [BRIDGE] SESSION SAVED: {tenant_id}:{persona_id}")

        print(f"👤 [BRIDGE] Final Identity -> Tenant: {tenant_id} | Persona: {persona_id}")

        response_data = await generate_twin_response(
            query=user_query,
            tenantId=tenant_id,
            system_prompt=ACTIVE_SYSTEM_PROMPT,  # formatted inside generate_twin_response
            personaId=persona_id,
            messages=messages[:-1]
        )
        
        if isinstance(response_data, dict):
            answer = response_data.get("answer", "")
        else:
            answer = str(response_data)

        return JSONResponse({
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "digital-brain",
            "content": answer,  # Flat key for custom OpenWebUI Filters/Pipelines
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ OpenAI Bridge Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("PORT", "3000"))

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║       Peak AI 1.0 MCP Server {VERSION:<30} ║
╠══════════════════════════════════════════════════════════════╣
║  ✓ Bedrock Converse API (Chat)                              ║
║  ✓ {EMBEDDING_PROVIDER.upper():<52} ║
║  ✓ Unified normalize_collection_name() (FIXED)             ║
║  ✓ Persona + Tenant Isolation                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    if transport == "sse":
        print(f"Starting HTTP server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")