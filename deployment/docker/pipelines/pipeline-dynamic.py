"""
title: CloneMind Dynamic Identity Pipeline
author: CloneMind AI
version: 1.0.0
requirements: requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel, Field
import requests
import json

class Pipe:
    class Valves(BaseModel):
        TENANT_SERVICE_URL: str = Field(
            default="http://tenant-service-dt:8000",
            description="URL for Tenant Management Service",
        )
        MCP_SERVER_URL: str = Field(
            default="http://mcp-server-dt:8080/sse",
            description="URL for MCP Knowledge Base Server",
        )

    def __init__(self):
        self.type = "manifold"
        self.id = "clonemind_proxy"
        self.name = "CloneMind: "
        self.valves = self.Valves()

    def pipes(self) -> List[dict]:
        return [{"id": "twin", "name": "AI Twin Mode"}]

    def get_tenant_dna(self, tenant_id: str):
        """Fetch the prompt DNA (tone, industry, etc.) from Tenant Service"""
        try:
            response = requests.get(f"{self.valves.TENANT_SERVICE_URL}/api/tenants/{tenant_id}", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching DNA: {e}")
        return None

    def get_rag_context(self, query: str, tenant_id: str):
        """Call MCP Server to get relevant document chunks via simple HTTP POST bridge"""
        try:
            mcp_url = self.valves.MCP_SERVER_URL.replace("/sse", "/call/search_knowledge_base")
            response = requests.post(
                mcp_url,
                json={"query": query, "tenantId": tenant_id},
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get("content", "No context found")
        except Exception as e:
            print(f"Error calling MCP: {e}")
        return "Knowledge Context placeholder..."

    def pipe(self, body: dict, __user__: dict = None) -> Union[str, Generator, Iterator]:
        # 1. Identify User & Tenant
        email = __user__.get("email", "unknown")
        
        # 2. Lookup Tenant Context via API
        try:
            lookup_resp = requests.get(f"{self.valves.TENANT_SERVICE_URL}/api/user/lookup", params={"email": email}, timeout=5)
            lookup = lookup_resp.json() if lookup_resp.status_code == 200 else {}
        except:
            lookup = {}

        tenant_id = lookup.get("tenantId", "default")
        persona_id = lookup.get("personaId", "user")
        
        # 3. Fetch Prompt DNA (Tone, Company Name)
        dna = self.get_tenant_dna(tenant_id)
        if dna:
            tenant_info = dna.get("tenant", {})
            company = tenant_info.get("companyName", "Unknown Corp")
            tone = tenant_info.get("tone", "professional")
            industry = tenant_info.get("industry", "Business")
            
            # 4. Construct the DYNAMIC SYSTEM PROMPT
            system_prompt = f"""You are the official AI Twin of {company}, operating in the {industry} industry.
Your mission is to represent {company} with a {tone} communication style.

### CORE BEHAVIOR:
1. **Fact-First**: Use the provided 'Knowledge Context' as your primary source of truth.
2. **Identity**: Never break character. You are part of {company}. Use "we" and "our" when referring to the company.
3. **Accuracy**: If the context doesn't contain the answer, politely state that you don't have that specific information but can help with other {industry}-related topics.
4. **Style**: Maintain a {tone} tone in every interaction.

Always prioritize the information found in the retrieved documents to provide accurate, industry-specific value."""
        else:
            system_prompt = "You are a helpful AI assistant representing a professional organization. Use the provided context to answer questions accurately."

        # 5. Get User Message
        user_message = body["messages"][-1]["content"]

        # 6. Call MCP Server for Full Response (including RAG and Model Routing)
        print(f"Sending request to MCP for tenant: {tenant_id}")
        try:
            # We'll call a combined 'generate_twin_response' tool on MCP via the HTTP bridge
            mcp_chat_url = self.valves.MCP_SERVER_URL.replace("/sse", "/call/generate_twin_response")
            payload = {
                "query": user_message,
                "tenantId": tenant_id,
                "system_prompt": system_prompt,
                "messages": body.get("messages", [])[:-1] # History
            }
            
            response = requests.post(mcp_chat_url, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("content", "No response from MCP")
            else:
                return f"Error from MCP Server: {response.status_code}"
                
        except Exception as e:
            print(f"MCP Call failed: {e}")
            return f"Error calling MCP: {str(e)}"
