import os
import asyncio
import json
import boto3
from typing import Optional, List
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "172.17.0.1")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# AWS Configuration - Use AWS_REGION if available (CDK standard), otherwise default
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
# Try Titan V2 first as it's the modern standard, fallback to V1
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
VECTOR_SIZE = 1024 # Default for Titan V2. Titan V1 is 1536.

# Initialize FastMCP server
mcp = FastMCP("CloneMind Knowledge Base")

# Initialize FastAPI for HTTP endpoints
app = FastAPI()

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

def get_embedding(text: str) -> List[float]:
    """Generate embedding using Bedrock Titan."""
    try:
        current_model = EMBEDDING_MODEL_ID
        print(f"Generating embedding for text (length: {len(text)}) using model {current_model} in region {AWS_REGION}")
        
        # Ensure text is not too long for Titan (approx 8k tokens, roughly 30k chars)
        if len(text) > 30000:
            print(f"Warning: Text is very long ({len(text)} chars), truncating to 30000")
            text = text[:30000]

        body_dict = {"inputText": text}
        # If using V2, we can specify dimensions to match our collection if needed, 
        # but 1024 is the high-quality default.
        
        body = json.dumps(body_dict)
        
        try:
            response = bedrock_client.invoke_model(
                body=body,
                modelId=current_model,
                accept="application/json",
                contentType="application/json"
            )
        except Exception as e:
            if "model is not available" in str(e).lower() and current_model == "amazon.titan-embed-text-v2:0":
                print("Titan V2 not available, falling back to V1...")
                current_model = "amazon.titan-embed-text-v1"
                # Note: This will fail if the collection was already created with 1024
                response = bedrock_client.invoke_model(
                    body=body,
                    modelId=current_model,
                    accept="application/json",
                    contentType="application/json"
                )
            else:
                raise

        response_body = json.loads(response.get("body").read())
        embedding = response_body.get("embedding")
        
        if not embedding:
            print(f"Error: Bedrock returned empty embedding. Response keys: {list(response_body.keys())}")
            raise Exception("Empty embedding returned from Bedrock")
        
        print(f"Successfully generated embedding (size: {len(embedding)}) using {current_model}")
        return embedding
    except Exception as e:
        print(f"Bedrock Embedding Error: {str(e)}")
        raise

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
            formatted_results.append(f"[Score: {res.score:.4f}] {text}")

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
        
        # 2. Intelligent Model selection (Router)
        # Fast: Claude 3.5 Haiku, Smart: Claude 3.5 Sonnet
        selected_model = "anthropic.claude-3-5-haiku-20241022-v1:0"
        
        q = query.lower()
        complex_keywords = ['compare', 'difference', 'calculate', 'optimize', 'why', 'explain']
        if any(k in q for k in complex_keywords) or len(q.split()) > 20:
            selected_model = "anthropic.claude-3-5-sonnet-20241022-v2:0"
            # Claude 3.5 Sonnet works best with a Chain of Thought instruction for complex queries
            system_prompt += "\n\nFor complex queries, please reason through the knowledge context step-by-step before providing your final answer to ensure maximum accuracy."
            print(f"Routing to Smart Model: {selected_model}")
        else:
            print(f"Routing to Fast Model: {selected_model}")

        # 3. Prepare Bedrock Call
        bedrock_messages = []
        if messages:
            for msg in messages[-5:]: # Last 5 for context
                role = "user" if msg.get("role") == "user" else "assistant"
                content = msg.get("content", "")
                if content:
                    bedrock_messages.append({"role": role, "content": [{"text": content}]})
        
        # Add current query with context formatted for better model comprehension
        rag_prompt = f"""<knowledge_context>
{context}
</knowledge_context>

Based on the knowledge context provided above, please answer the following user query. If the answer is not in the context, use your general knowledge but prioritize the context.

User Query: {query}"""
        bedrock_messages.append({"role": "user", "content": [{"text": rag_prompt}]})

        # 4. Invoke Bedrock
        response = bedrock_client.invoke_model(
            modelId=selected_model,
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
        return answer

    except Exception as e:
        return f"MCP Error generating response: {str(e)}"

@mcp.tool()
async def ingest_knowledge(text: str, tenantId: str, metadata: Optional[dict] = None) -> str:
    """
    Ingest information into a tenant's private collection.
    """
    try:
        print(f"Ingesting knowledge for tenant: {tenantId}")
        collection_name = tenantId.replace("-", "_")
        
        if not text or not text.strip():
            print("Warning: Received empty text for ingestion")
            return "Error: Text content is empty."

        # 1. Get embedding first to know the size
        vector = get_embedding(text)
        vector_size = len(vector)
        
        # 2. Ensure collection matches embedding size
        ensure_collection(collection_name, vector_size)
        
        payload = {"text": text, "tenantId": tenantId, **(metadata or {})}
        
        import uuid
        point_id = str(uuid.uuid4())
        print(f"Upserting point {point_id} to collection {collection_name} (vector size: {vector_size})")
        
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)]
        )
        print(f"Successfully ingested information for {tenantId}.")
        return f"Successfully ingested information for {tenantId}."
    except Exception as e:
        print(f"Critical Ingestion Error: {str(e)}")
        return f"Error ingesting knowledge: {str(e)}"

# FastAPI HTTP Bridge for the Pipeline
@app.get("/")
async def health_check():
    return JSONResponse({"status": "healthy", "service": "CloneMind MCP Server"})

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

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
    
    if transport == "sse":
        # Run FastAPI server for SSE/HTTP mode
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Run MCP in stdio mode
        mcp.run(transport="stdio")