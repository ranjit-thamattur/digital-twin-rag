import os
import asyncio
import json
import boto3
from typing import Optional, List
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6334"))
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"
VECTOR_SIZE = 1536 # Titan embedding size

# Initialize FastMCP server
mcp = FastMCP("CloneMind Knowledge Base")

# Initialize Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

def get_embedding(text: str) -> List[float]:
    """Generate embedding using Bedrock Titan."""
    body = json.dumps({"inputText": text})
    response = bedrock_client.invoke_model(
        body=body,
        modelId=EMBEDDING_MODEL_ID,
        accept="application/json",
        contentType="application/json"
    )
    response_body = json.loads(response.get("body").read())
    return response_body.get("embedding")

def ensure_collection(collection_name: str):
    """Ensure a Qdrant collection exists for the tenant."""
    if not qdrant_client.collection_exists(collection_name):
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )

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
        collection_name = tenantId.replace("-", "_")
        ensure_collection(collection_name)
        vector = get_embedding(text)
        payload = {"text": text, "tenantId": tenantId, **(metadata or {})}
        
        import uuid
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[models.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload)]
        )
        return f"Successfully ingested information for {tenantId}."
    except Exception as e:
        return f"Error ingesting knowledge: {str(e)}"

# Simple HTTP Bridge for the Pipeline
from starlette.responses import JSONResponse
from starlette.requests import Request

@mcp.app.route("/call/{tool_name}", methods=["POST"])
async def call_tool_bridge(request: Request):
    tool_name = request.path_params["tool_name"]
    try:
        arguments = await request.json()
        if tool_name == "generate_twin_response":
            result = await generate_twin_response(**arguments)
        elif tool_name == "search_knowledge_base":
            result = await search_knowledge_base(**arguments)
        else:
            return JSONResponse({"error": f"Tool {tool_name} not found in bridge"}, status_code=404)
        
        return JSONResponse({"content": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=8080)
    else:
        mcp.run(transport="stdio")
