"""
title: Peak AI 1.0 Pipeline (Multi-tenant)
author: Peak AI 1.0
date: 2024-01-13
version: 2.0
license: MIT
description: RAG pipeline that passes tenant/persona metadata to n8n workflow
requirements: requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests
import os


class Pipeline:
    class Valves(BaseModel):
        # MCP Configuration
        MCP_API_URL: str = "http://mcp-server:3000/call/generate_twin_response"
        ENABLE_TENANT_FILTERING: bool = True
        DEFAULT_TENANT_ID: str = "default"
        DEFAULT_PERSONA_ID: str = "default"
        
    def __init__(self):
        self.type = "pipe"
        self.name = "Peak AI 1.0: Your Digital Brain"
        self.valves = self.Valves()
        
    async def on_startup(self):
        print(f"✅ Digital Brain Native Pipeline loaded")
        print(f"   MCP URL: {self.valves.MCP_API_URL}")
        
    async def on_shutdown(self):
        print("👋 Digital Brain Native Pipeline shutting down")

    def get_tenant_info(self, __user__: dict) -> tuple:
        """Extract tenant/persona metadata."""
        user_metadata = __user__.get("metadata", {})
        if "tenantId" in user_metadata:
            return user_metadata["tenantId"], user_metadata.get("personaId", "default")
        
        email = __user__.get("email", "")
        if email and "@" in email:
            domain = email.split("@")[1].replace(".", "-")
            return f"tenant-{domain}", f"persona-{email.split('@')[0]}"
        
        return self.valves.DEFAULT_TENANT_ID, self.valves.DEFAULT_PERSONA_ID

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        
        # 1. Identity Trace
        __user__ = body.get("user", {})
        tenant_id, persona_id = self.get_tenant_info(__user__)
        
        print(f"📨 Digital Brain Query: {user_message[:50]}... ({tenant_id})")
        
        try:
            # 2. Call Digital Brain MCP Directly
            payload = {
                "query": user_message,
                "tenantId": tenant_id,
                "personaId": persona_id,
                "chat_history": messages[:-1] # History excluding current message
            }
            
            response = requests.post(
                self.valves.MCP_API_URL,
                json=payload,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                # MCP bridge returns {"content": "..."}
                answer = result.get("content", "No response received")
                return answer
            else:
                error_msg = f"Digital Brain Error: {response.status_code} - {response.text}"
                print(f"   ❌ {error_msg}")
                return error_msg
                
        except Exception as e:
            print(f"   ❌ Connection Error: {str(e)}")
            return f"Error connecting to Digital Brain: {str(e)}"
