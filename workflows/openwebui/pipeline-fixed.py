"""
title: Digital Twin RAG (Simple Multi-tenant)
author: open-webui
date: 2024-01-13
version: 1.0
license: MIT
description: Simple RAG pipeline - manually configure tenant/persona in pipeline settings
requirements: requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests


class Pipeline:
    class Valves(BaseModel):
        # n8n configuration
        N8N_WEBHOOK_URL: str = "http://n8n-dt:5678/webhook/openwebui"
        
        # Tenant configuration - CHANGE THESE
        TENANT_ID: str = "tenant-123"
        PERSONA_ID: str = "persona-user"
        
        # Set to True to use tenant filtering
        ENABLE_FILTERING: bool = True
        
    def __init__(self):
        self.type = "filter"
        self.name = "Digital Twin RAG (Simple)"
        self.valves = self.Valves()
        
    async def on_startup(self):
        print(f"✅ Digital Twin RAG Pipeline loaded")
        print(f"   Tenant: {self.valves.TENANT_ID}")
        print(f"   Persona: {self.valves.PERSONA_ID}")
        print(f"   Filtering: {self.valves.ENABLE_FILTERING}")

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        
        print(f"📨 Query: {user_message[:50]}...")
        
        try:
            # Build payload
            payload = {
                "message": user_message
            }
            
            # Add tenant/persona if filtering enabled
            if self.valves.ENABLE_FILTERING:
                payload["tenantId"] = self.valves.TENANT_ID
                payload["personaId"] = self.valves.PERSONA_ID
                print(f"   Using: {self.valves.TENANT_ID}/{self.valves.PERSONA_ID}")
            
            # Call n8n
            response = requests.post(
                self.valves.N8N_WEBHOOK_URL,
                json=payload,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "No response")
            else:
                return f"Error: n8n returned {response.status_code}"
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return f"Error: {str(e)}"
