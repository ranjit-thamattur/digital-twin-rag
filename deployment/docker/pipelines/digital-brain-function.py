"""
title: Digital Brain: Direct MCP Integration
author: Peak AI
date: 2026-05-12
version: 1.0
license: MIT
description: A direct integration function for OpenWebUI that calls the Digital Brain MCP server natively.
requirements: requests
"""

from typing import List, Union, Generator, Iterator, Optional
from pydantic import BaseModel
import requests
import json
import os

class Filter:
    class Valves(BaseModel):
        # MCP Configuration
        MCP_API_URL: str = "http://mcp-server:3000/call/generate_twin_response"
        ENABLE_DIRECT_MCP: bool = True
        
    def __init__(self):
        self.type = "filter"
        self.name = "Digital Brain Native"
        self.valves = self.Valves()
        
    async def on_startup(self):
        print(f"🧠 Digital Brain Native Filter loaded")
        print(f"   Target: {self.valves.MCP_API_URL}")
        
    async def on_shutdown(self):
        print("👋 Digital Brain Native Filter shutting down")

    def get_user_metadata(self, __user__: dict) -> tuple:
        """Extract tenant/persona from user metadata or email."""
        metadata = __user__.get("metadata", {})
        tenant_id = metadata.get("tenantId", "default")
        persona_id = metadata.get("personaId", "default")
        
        # Fallback to email domain if metadata missing
        if tenant_id == "default":
            email = __user__.get("email", "")
            if "@" in email:
                tenant_id = f"tenant-{email.split('@')[1].replace('.', '-')}"
                persona_id = f"persona-{email.split('@')[0]}"
        
        return tenant_id, persona_id

    async def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """
        Detect if we should intercept the query and route to Digital Brain MCP.
        This runs BEFORE the message is sent to the LLM.
        """
        if not self.valves.ENABLE_DIRECT_MCP:
            return body

        # Check if the model selected is 'digital-brain'
        model_id = body.get("model", "")
        if "digital-brain" not in model_id.lower():
            return body

        print(f"🎯 Intercepting query for Digital Brain native processing...")
        return body

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        """
        The main pipeline execution.
        Calls the MCP server's HTTP bridge directly.
        """
        
        # 1. Identity Verification
        __user__ = body.get("user", {})
        tenant_id, persona_id = self.get_user_metadata(__user__)
        
        print(f"🧠 [Digital Brain] Query: '{user_message[:50]}...'")
        print(f"   Identity: {tenant_id} / {persona_id}")
        
        # 2. Call MCP Bridge
        try:
            payload = {
                "query": user_message,
                "tenantId": tenant_id,
                "personaId": persona_id,
                "chat_history": messages[:-1] # Exclude current message
            }
            
            response = requests.post(
                self.valves.MCP_API_URL,
                json=payload,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                # MCP bridge returns {"content": "..."}
                answer = result.get("content", "Error: Empty response from Digital Brain.")
                print(f"   ✅ Success: {len(answer)} chars")
                return answer
            else:
                error_detail = response.text
                print(f"   ❌ Error {response.status_code}: {error_detail}")
                return f"Digital Brain Error ({response.status_code}): {error_detail}"
                
        except Exception as e:
            print(f"   ❌ Connection Error: {str(e)}")
            return f"Failed to connect to Digital Brain: {str(e)}"
