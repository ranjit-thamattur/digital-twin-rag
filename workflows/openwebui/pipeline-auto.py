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
        # Pipeline configuration
        N8N_WEBHOOK_URL: str = "http://n8n-dt:5678/webhook/openwebui"
        ENABLE_TENANT_FILTERING: bool = True
        DEFAULT_TENANT_ID: str = "default"
        DEFAULT_PERSONA_ID: str = "default"
        
    def __init__(self):
        self.type = "filter"
        self.name = "Peak AI 1.0: Your Digital Twin"
        self.valves = self.Valves()
        
    async def on_startup(self):
        print(f"✅ Digital Twin RAG Pipeline loaded")
        print(f"   n8n URL: {self.valves.N8N_WEBHOOK_URL}")
        print(f"   Multi-tenant: {self.valves.ENABLE_TENANT_FILTERING}")
        
    async def on_shutdown(self):
        print("👋 Digital Twin RAG Pipeline shutting down")

    def get_tenant_info(self, __user__: dict) -> tuple:
        """
        Extract tenant/persona from user object
        
        Strategies:
        1. From user metadata (if set in Open WebUI admin)
        2. From user email domain
        3. From user ID
        4. Default values
        """
        
        if not self.valves.ENABLE_TENANT_FILTERING:
            return self.valves.DEFAULT_TENANT_ID, self.valves.DEFAULT_PERSONA_ID
        
        # Strategy 1: Check user metadata
        user_metadata = __user__.get("metadata", {})
        if "tenantId" in user_metadata and "personaId" in user_metadata:
            return user_metadata["tenantId"], user_metadata["personaId"]
        
        # Strategy 2: Use email domain as tenant
        email = __user__.get("email", "")
        if email and "@" in email:
            domain = email.split("@")[1].replace(".", "-")
            tenant_id = f"tenant-{domain}"
            persona_id = f"persona-{email.split('@')[0]}"
            return tenant_id, persona_id
        
        # Strategy 3: Use user ID
        user_id = __user__.get("id", "")
        if user_id:
            return f"tenant-{user_id[:8]}", f"persona-{user_id[:8]}"
        
        # Strategy 4: Default
        return self.valves.DEFAULT_TENANT_ID, self.valves.DEFAULT_PERSONA_ID

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        
        print(f"📨 Digital Twin RAG Query: {user_message[:50]}...")
        
        # Get user info
        __user__ = body.get("user", {})
        tenant_id, persona_id = self.get_tenant_info(__user__)
        
        print(f"   Tenant: {tenant_id}")
        print(f"   Persona: {persona_id}")
        
        try:
            # Call n8n workflow with tenant/persona metadata
            payload = {
                "message": user_message,
                "tenantId": tenant_id,
                "personaId": persona_id,
                "userId": __user__.get("id", ""),
                "userEmail": __user__.get("email", "")
            }
            
            print(f"   Calling n8n: {self.valves.N8N_WEBHOOK_URL}")
            
            response = requests.post(
                self.valves.N8N_WEBHOOK_URL,
                json=payload,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get("response", "No response received")
                
                print(f"   ✅ Response received ({len(answer)} chars)")
                return answer
            else:
                error_msg = f"n8n error: {response.status_code}"
                print(f"   ❌ {error_msg}")
                return f"Error: {error_msg}"
                
        except requests.exceptions.Timeout:
            print("   ⏱️  Request timeout")
            return "Error: Request timed out. Try a simpler query or check n8n workflow."
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return f"Error: {str(e)}"
