"""
title: Self² AI with RAG (Debug Version)
author: self2ai
version: 3.0.1-debug
requirements: requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel, Field
import requests
import json


class Pipe:
    class Valves(BaseModel):
        N8N_WEBHOOK_URL: str = Field(
            default="http://n8n-dt:5678/webhook/openwebui",
            description="n8n webhook URL for chat",
        )
        N8N_UPLOAD_URL: str = Field(
            default="http://n8n-dt:5678/webhook/upload-document",
            description="n8n webhook URL for file uploads",
        )
        TENANT_MODE: str = Field(
            default="email_domain",
            description="Tenant assignment mode: email_domain, email_username, user_id, fixed",
        )
        DEFAULT_TENANT: str = Field(
            default="default-tenant",
            description="Fallback tenant if user info unavailable",
        )
        DEFAULT_PERSONA: str = Field(
            default="user", description="Default persona for users"
        )
        TENANT_MAPPING: str = Field(
            default="{}", description="JSON mapping of email to tenant (optional)"
        )
        DEBUG_MODE: bool = Field(
            default=True, description="Enable detailed debug logging"
        )

    def __init__(self):
        self.type = "manifold"
        self.id = "self2ai"
        self.name = "Self² AI: "
        self.valves = self.Valves()
    
    # Persona assignments (email -> persona mapping)
    PERSONA_MAP = {
        # Tenant A users
        "alice.tenanta@gmail.com": "CEO",
        "bob.tenanta@gmail.com": "manager",
        "sarah.tenanta@gmail.com": "analyst",
        
        # Tenant B users
        "diana.tenantb@gmail.com": "CEO",
        "john.tenantb@gmail.com": "manager",
        
        # Demo tenant
        "demo.demotenant@gmail.com": "CEO",
        
        # Add more users here as needed
        # "user@domain.com": "persona",
    }

    def pipes(self) -> List[dict]:
        return [{"id": "self2ai_rag", "name": "Self² AI RAG"}]

    def get_tenant_persona(self, user_info: dict, __user__: dict = None) -> tuple:
        """Extract tenant and persona from user info"""

        if self.valves.DEBUG_MODE:
            print(f"\n{'='*60}")
            print(f"[Self² AI DEBUG] Full user_info received:")
            print(json.dumps(user_info, indent=2, default=str))
            if __user__:
                print(f"\n[Self² AI DEBUG] Full __user__ received:")
                print(json.dumps(__user__, indent=2, default=str))
            print(f"{'='*60}\n")

        # Try multiple sources for email
        email = None

        # Source 1: user_info dict
        email = user_info.get("email", "")
        if email:
            print(f"[Self² AI] ✓ Found email in user_info: {email}")

        # Source 2: __user__ parameter (Open WebUI passes this)
        if not email and __user__:
            email = __user__.get("email", "")
            if email:
                print(f"[Self² AI] ✓ Found email in __user__: {email}")

        # Source 3: username field
        if not email:
            username = user_info.get("username", "") or user_info.get("name", "")
            if username and "@" in username:
                email = username
                print(f"[Self² AI] ✓ Found email in username: {email}")

        # Get other user data
        user_id = user_info.get("id", "")
        role = user_info.get("role", "user")

        print(f"[Self² AI] Extracted - Email: {email}, ID: {user_id}, Role: {role}")

        # Check tenant mapping
        try:
            tenant_map = json.loads(self.valves.TENANT_MAPPING)
        except:
            tenant_map = {}

        if email and email in tenant_map:
            tenant_id = tenant_map[email]
            persona_id = role
            print(f"[Self² AI] ✓ Mapped from open_webui.config: {tenant_id} / {persona_id}")
            return tenant_id, persona_id

        # Process based on mode
        if self.valves.TENANT_MODE == "email_domain":
            if email and "@" in email:
                username = email.split("@")[0]

                # Pattern: alice.tenantb@gmail.com -> extract "tenantb"
                if "." in username:
                    parts = username.split(".")
                    tenant_part = parts[-1]  # Last part after dot
                    tenant_id = f"tenant-{tenant_part}"
                    print(f"[Self² AI] ✓ Extracted from username pattern: {tenant_id}")
                else:
                    # No dot in username, use whole username
                    tenant_id = f"tenant-{username}"
                    print(f"[Self² AI] ✓ Using username as tenant: {tenant_id}")

                persona_id = role or "user"
            else:
                tenant_id = self.valves.DEFAULT_TENANT
                persona_id = self.valves.DEFAULT_PERSONA
                print(f"[Self² AI] ⚠️ No email found, using defaults")

        elif self.valves.TENANT_MODE == "email_username":
            if email and "@" in email:
                username = email.split("@")[0]
                tenant_id = f"tenant-{username}"
                persona_id = f"persona-{username}"
            else:
                tenant_id = self.valves.DEFAULT_TENANT
                persona_id = self.valves.DEFAULT_PERSONA

        elif self.valves.TENANT_MODE == "user_id":
            if user_id:
                tenant_id = f"tenant-{user_id[:8]}"
                persona_id = role or "user"
            else:
                tenant_id = self.valves.DEFAULT_TENANT
                persona_id = self.valves.DEFAULT_PERSONA

        else:  # fixed mode
            tenant_id = self.valves.DEFAULT_TENANT
            persona_id = self.valves.DEFAULT_PERSONA

        # Extract persona from email mapping
        if __user__:
            email = __user__.get("email", "")
            persona_id = self.PERSONA_MAP.get(email, "user")  # Default to "user"
            
            if persona_id != "user":
                print(f"[Self² AI] ✓ Mapped persona for {email}: {persona_id}")
            else:
                print(f"[Self² AI] ℹ️  No persona mapping for {email}, using default: user")

        print(f"[Self² AI] ✅ Final Assignment: {tenant_id} / {persona_id}")
        return tenant_id, persona_id

    def pipe(
        self, body: dict, __user__: dict = None
    ) -> Union[str, Generator, Iterator]:
        """Main pipeline entry point"""

        if self.valves.DEBUG_MODE:
            print(f"\n{'='*60}")
            print(f"[Self² AI DEBUG] Full body received:")
            print(
                json.dumps(
                    {k: v for k, v in body.items() if k != "messages"},
                    indent=2,
                    default=str,
                )
            )
            if __user__:
                print(f"\n[Self² AI DEBUG] __user__ parameter:")
                print(json.dumps(__user__, indent=2, default=str))
            print(f"{'='*60}\n")

        messages = body.get("messages", [])
        model_id = body.get("model", "unknown")
        user_info = body.get("user", {})

        # Extract tenant and persona - pass __user__ parameter
        tenant_id, persona_id = self.get_tenant_persona(user_info, __user__)

        # Get user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        print(f"[Self² AI] Query: {user_message[:100]}")

        # Skip internal tasks
        if user_message.startswith("###"):
            return ""

        # Call N8N RAG
        try:
            chat_payload = {
                "message": user_message,
                "messages": messages,
                "model": model_id,
                "tenantId": tenant_id,
                "personaId": persona_id,
            }

            print(
                f"[Self² AI] 📤 Sending to n8n: tenant={tenant_id}, persona={persona_id}"
            )

            response = requests.post(
                self.valves.N8N_WEBHOOK_URL,
                json=chat_payload,
                timeout=60,
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result.get(
                    "answer", result.get("response", str(result))
                )
                print(f"[Self² AI] ✅ Response received ({len(response_text)} chars)")
                return response_text
            else:
                error_msg = f"Error querying knowledge base: {response.status_code}"
                print(f"[Self² AI] ❌ {error_msg}")
                return error_msg

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"[Self² AI] ❌ Exception: {error_msg}")
            return error_msg
