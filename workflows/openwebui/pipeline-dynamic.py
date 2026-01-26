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
            default="http://172.17.0.1:8000",
            description="URL for Tenant Management Service (Local Bridge)",
        )
        MCP_SERVER_URL: str = Field(
            default="http://172.17.0.1:3000/sse",
            description="URL for MCP Knowledge Base Server (Local Bridge)",
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
            response = requests.get(f"{self.valves.TENANT_SERVICE_URL}/api/tenants/{tenant_id}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching DNA: {e}")
        return None

    def get_rag_context(self, query: str, tenant_id: str):
        """Call MCP Server to get relevant document chunks via simple HTTP POST"""
        try:
            # We assume a bridge exists or the MCP server exposes a REST endpoint for convenience
            # Otherwise, we'd need a full MCP SSE client here.
            # For now, we'll use a direct tool call if possible, or fallback to placeholder.
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
        
        # 2. Lookup Tenant Context
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
            company = dna.get("companyName", "Unknown Corp")
            tone = dna.get("tone", "professional")
            industry = dna.get("industry", "Business")
            instructions = dna.get("specialInstructions", "")
            
            # Fetch Persona Detail
            personas = dna.get("personas", {})
            persona_config = personas.get(persona_id, {"focus": "general", "style": "helpful"})
            focus = persona_config.get("focus", "general")
            style = persona_config.get("style", "professional")
            
            # 4. Construct the DYNAMIC SYSTEM PROMPT
            system_prompt = f"You are the AI Twin of the {persona_id} at {company} ({industry} industry). "
            system_prompt += f"Your communication style is {tone} and your persona focus is {focus}. "
            system_prompt += f"Adopt a {style} style of speaking. "
            if instructions:
                system_prompt += f"\nSpecial Guidelines: {instructions}"
            system_prompt += "\nUse the provided knowledge context to answer accurately and cite your sources."
        else:
            system_prompt = "You are a helpful AI assistant."

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
