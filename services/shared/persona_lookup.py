import requests
from typing import Tuple

TENANT_SERVICE_URL = "http://tenant-service-dt:8000"

def get_user_tenant_persona(email: str) -> Tuple[str, str]:
    """
    Get user's tenant and persona from tenant service API.
    Falls back to default if user not found.
    
    Args:
        email: User's email address
        
    Returns:
        Tuple of (tenant_id, persona_id)
    """
    try:
        response = requests.get(
            f"{TENANT_SERVICE_URL}/api/user/lookup",
            params={"email": email},
            timeout=2
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data["tenantId"], data["personaId"]
        
        # Fallback to default
        return "default", "user"
        
    except Exception as e:
        print(f"[WARN] Failed to lookup user {email}: {e}")
        # Fallback if tenant service unavailable
        return "default", "user"


# Backwards compatibility: PERSONA_MAP for offline/fallback mode
PERSONA_MAP_FALLBACK = {
    "alice.tenanta@gmail.com": ("tenant-tenanta", "CEO"),
    "bob.tenanta@gmail.com": ("tenant-tenanta", "manager"),
    "sarah.tenanta@gmail.com": ("tenant-tenanta", "analyst"),
    "diana.tenantb@gmail.com": ("tenant-tenantb", "CEO"),
    "john.tenantb@gmail.com": ("tenant-tenantb", "manager"),
    "demo.demotenant@gmail.com": ("tenant-demotenant", "CEO"),
}

def get_user_tenant_persona_with_fallback(email: str) -> Tuple[str, str]:
    """
    Try API first, fall back to hardcoded map if API unavailable.
    """
    try:
        # Try API first
        return get_user_tenant_persona(email)
    except:
        # Fall back to hardcoded map
        if email in PERSONA_MAP_FALLBACK:
            return PERSONA_MAP_FALLBACK[email]
        return "default", "user"
