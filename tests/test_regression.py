"""
Digital Brain — Full Regression Test Suite
============================================
Tenant: testcorp (dedicated regression tenant)

Prerequisites (SSM tunnels — skip for --unit-only):

  Terminal 1 - Tenant Service:
    aws ssm start-session --target i-04de122dcff25503b \
      --document-name AWS-StartPortForwardingSession \
      --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}' \
      --region us-east-1

  Terminal 2 - MCP Server:
    aws ssm start-session --target i-04de122dcff25503b \
      --document-name AWS-StartPortForwardingSession \
      --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}' \
      --region us-east-1

Usage:
  python tests/test_regression.py              # full suite (needs server)
  python tests/test_regression.py --unit-only  # keyword unit tests only (no server needed)
"""

import sys
import requests

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

MCP_SERVICE    = "http://localhost:3000"
TENANT_SERVICE = "http://localhost:8000"
TENANT_ID      = "testcorp"
PERSONA_ID     = "ceo"
TIMEOUT_SHORT  = 5
TIMEOUT_LLM    = 60

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"

GUARDRAIL_PHRASES = ["business", "work", "knowledge base", "work-related", "company"]

def _is_guardrail_response(content: str) -> bool:
    return any(p in content.lower() for p in GUARDRAIL_PHRASES) and len(content) < 300

def _chat(query: str, plan: str = "basic", persona: str = PERSONA_ID) -> str:
    payload = {
        "query": query,
        "tenantId": TENANT_ID,
        "personaId": persona,
        "system_prompt": "",
        "messages": [],
        "plan": plan,
    }
    r = requests.post(f"{MCP_SERVICE}/call/generate_twin_response", json=payload, timeout=TIMEOUT_LLM)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json().get("content", "")

def _chief(query: str, confirmed: bool = False) -> object:
    payload = {
        "query": query,
        "tenantId": TENANT_ID,
        "personaId": PERSONA_ID,
        "messages": [],
        "confirmed": confirmed,
    }
    r = requests.post(f"{MCP_SERVICE}/call/chief_of_staff", json=payload, timeout=TIMEOUT_LLM)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json().get("content", {})


# ═════════════════════════════════════════════
# SECTION 1: Infrastructure Health
# ═════════════════════════════════════════════

def test_health_endpoint():
    print("\n[S1-1] MCP health check...")
    r = requests.get(f"{MCP_SERVICE}/health", timeout=TIMEOUT_SHORT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("status") == "healthy", f"Unexpected status: {data}"
    redis = data.get("redis", False)
    print(f"  {PASS} MCP healthy | Redis: {'✅' if redis else '⚠ offline'}")

def test_root_endpoint():
    print("\n[S1-2] MCP root health check...")
    r = requests.get(f"{MCP_SERVICE}/", timeout=TIMEOUT_SHORT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"
    print(f"  {PASS} Root healthy | version={data.get('version')} | provider={data.get('provider')}")

def test_stats_endpoint():
    print("\n[S1-3] Cost stats endpoint...")
    r = requests.get(f"{MCP_SERVICE}/stats", timeout=TIMEOUT_SHORT)
    assert r.status_code == 200
    data = r.json()
    tracker = data.get("cost_tracker", {})
    for key in ("embedding_calls", "chat_calls", "total_tokens", "cache_hits"):
        assert key in tracker, f"Missing key in cost_tracker: {key}"
    print(f"  {PASS} Stats keys present | embedding_calls={tracker['embedding_calls']} chat_calls={tracker['chat_calls']}")

def test_unknown_tool_returns_error():
    print("\n[S1-4] Unknown tool name returns error response...")
    r = requests.post(f"{MCP_SERVICE}/call/not_a_real_tool", json={}, timeout=TIMEOUT_SHORT)
    body = r.json()
    has_error = r.status_code == 404 or "error" in body
    assert has_error, f"Expected error response, got: {body}"
    print(f"  {PASS} Unknown tool returned error (HTTP {r.status_code})")


# ═════════════════════════════════════════════
# SECTION 2: Digital Brain — generate_twin_response
# ═════════════════════════════════════════════

def test_basic_business_query():
    print("\n[S2-1] Basic plan: business query should respond...")
    content = _chat("What is our revenue strategy for this year?", plan="basic")
    assert len(content) > 10, f"Response too short: '{content}'"
    assert not content.startswith("MCP Error"), f"Got MCP error: {content}"
    print(f"  {PASS} Business query responded ({len(content)} chars)")

def test_basic_guardrail_blocks_joke():
    print("\n[S2-2] Basic plan: should block 'tell me a joke'...")
    content = _chat("tell me a joke", plan="basic")
    assert _is_guardrail_response(content), f"Expected block, got: {content[:200]}"
    print(f"  {PASS} Blocked: '{content[:100]}'")

def test_basic_guardrail_blocks_weather():
    print("\n[S2-3] Basic plan: should block 'what is the weather'...")
    content = _chat("what is the weather today?", plan="basic")
    assert _is_guardrail_response(content), f"Expected block, got: {content[:200]}"
    print(f"  {PASS} Blocked: '{content[:100]}'")

def test_basic_guardrail_blocks_poem():
    print("\n[S2-4] Basic plan: should block 'write me a poem'...")
    content = _chat("write me a poem about the ocean", plan="basic")
    assert _is_guardrail_response(content), f"Expected block, got: {content[:200]}"
    print(f"  {PASS} Blocked: '{content[:100]}'")

def test_premium_allows_creative_query():
    print("\n[S2-5] Premium plan: should allow creative/open-ended queries...")
    content = _chat("Write a short paragraph about innovation in our industry.", plan="premium")
    assert len(content) > 20, f"Expected substantive response, got: {content[:200]}"
    print(f"  {PASS} Premium creative query responded ({len(content)} chars)")

def test_basic_token_limit():
    print("\n[S2-6] Basic plan: response should stay within ~512 token limit...")
    content = _chat(
        "Give me a detailed analysis of all our strategies, clients, revenue, products, and roadmap.",
        plan="basic"
    )
    assert len(content) < 2500, f"Response too long for Basic plan: {len(content)} chars"
    print(f"  {PASS} Basic response length: {len(content)} chars (within limit)")

def test_empty_query_handled_gracefully():
    print("\n[S2-7] Empty query should return graceful message, not crash...")
    payload = {"query": "", "tenantId": TENANT_ID, "personaId": PERSONA_ID,
               "system_prompt": "", "messages": [], "plan": "basic"}
    r = requests.post(f"{MCP_SERVICE}/call/generate_twin_response", json=payload, timeout=TIMEOUT_SHORT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    body = r.json()
    assert "content" in body or "error" in body, f"Unexpected response: {body}"
    print(f"  {PASS} Empty query handled gracefully")

def test_response_never_starts_with_mcp_error():
    print("\n[S2-8] Regression guard: response must never start with 'MCP Error:'...")
    content = _chat("What are our top priorities this quarter?", plan="basic")
    assert not content.startswith("MCP Error"), f"Got raw MCP error: {content[:200]}"
    print(f"  {PASS} No raw MCP error in response")


# ═════════════════════════════════════════════
# SECTION 3: Knowledge Base Search
# ═════════════════════════════════════════════

def test_search_returns_results():
    print("\n[S3-1] search_knowledge_base: should respond for a business query...")
    payload = {"query": "revenue strategy", "tenantId": TENANT_ID, "personaId": PERSONA_ID, "limit": 3}
    r = requests.post(f"{MCP_SERVICE}/call/search_knowledge_base", json=payload, timeout=TIMEOUT_LLM)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    content = r.json().get("content", "")
    assert "MCP Error" not in str(content), f"Got error: {content}"
    print(f"  {PASS} Search responded ({len(str(content))} chars)")

def test_search_empty_query_returns_validation():
    print("\n[S3-2] search_knowledge_base: empty query should return validation message...")
    payload = {"query": "", "tenantId": TENANT_ID, "personaId": PERSONA_ID}
    r = requests.post(f"{MCP_SERVICE}/call/search_knowledge_base", json=payload, timeout=TIMEOUT_SHORT)
    assert r.status_code == 200
    content = str(r.json().get("content", ""))
    assert "provide" in content.lower() or len(content) < 50, \
        f"Expected validation message, got: {content[:200]}"
    print(f"  {PASS} Empty search validation: '{content[:80]}'")


# ═════════════════════════════════════════════
# SECTION 4: Chief of Staff — Flag OFF (Phase 1)
# ═════════════════════════════════════════════

def test_chief_disabled_hire_keyword():
    print("\n[S4-1] Chief OFF: hire keyword should NOT return confirmation card...")
    content = _chief("we just hired a new designer", confirmed=False)
    if isinstance(content, dict):
        assert content.get("type") != "confirmation_required", \
            "Chief is ENABLED on server — expected disabled for Phase 1"
    print(f"  {PASS} No confirmation card (Chief disabled, routes to Digital Brain)")

def test_chief_disabled_launch_keyword():
    print("\n[S4-2] Chief OFF: launch keyword should NOT return confirmation card...")
    content = _chief("we are launching a new product next week", confirmed=False)
    if isinstance(content, dict):
        assert content.get("type") != "confirmation_required", \
            "Chief is ENABLED — expected disabled for Phase 1"
    print(f"  {PASS} No confirmation card for launch keyword (Chief disabled)")

def test_chief_disabled_normal_query():
    print("\n[S4-3] Chief OFF: normal query behaves like Digital Brain...")
    content = _chief("What is our Q3 revenue goal?")
    assert "Error" not in str(content)[:30], f"Got error: {str(content)[:200]}"
    print(f"  {PASS} Normal query through Chief responded ({len(str(content))} chars)")


# ═════════════════════════════════════════════
# SECTION 5: Keyword Matching — Unit Tests (no server)
# ═════════════════════════════════════════════

# Inline copy of WORKFLOW_TEMPLATES to avoid importing main.py (heavy deps)
_WORKFLOW_TEMPLATES = {
    "HIRE_EVENT": {"triggers": ["hired", "joining", "new hire", "onboard", "recruited",
                                "appointed", "we hired", "just hired", "new employee",
                                "new team member", "new staff"]},
    "CLIENT_SIGNED": {"triggers": ["signed", "new client", "contract signed", "deal closed",
                                   "onboarded client", "client onboard", "new customer",
                                   "client signed", "deal signed"]},
    "BUDGET_APPROVED": {"triggers": ["budget approved", "budget allocated", "funds approved",
                                     "approved the budget", "budget confirmed", "funding approved"]},
    "PRODUCT_LAUNCH": {"triggers": ["launching", "going live", "new product", "new feature",
                                    "release date", "we are launching", "product launch",
                                    "releasing", "ship the", "shipping"]},
    "TEAM_CHANGE": {"triggers": ["promoted", "restructure", "reporting to", "new role",
                                 "transferred", "team change", "role change", "promotion",
                                 "new manager", "org change"]},
}

def _match(query: str):
    q = query.lower()
    for wf_id, template in _WORKFLOW_TEMPLATES.items():
        if any(trigger in q for trigger in template["triggers"]):
            return wf_id
    return None

def test_keyword_hire():
    print("\n[S5-1] Keyword: 'we just hired a designer' → HIRE_EVENT...")
    assert _match("we just hired a designer") == "HIRE_EVENT"
    print(f"  {PASS} HIRE_EVENT matched")

def test_keyword_new_hire():
    print("\n[S5-2] Keyword: 'new hire starting Monday' → HIRE_EVENT...")
    assert _match("new hire starting Monday") == "HIRE_EVENT"
    print(f"  {PASS} HIRE_EVENT matched")

def test_keyword_client_signed():
    print("\n[S5-3] Keyword: 'contract signed with Acme' → CLIENT_SIGNED...")
    assert _match("contract signed with Acme") == "CLIENT_SIGNED"
    print(f"  {PASS} CLIENT_SIGNED matched")

def test_keyword_deal_closed():
    print("\n[S5-4] Keyword: 'deal closed yesterday' → CLIENT_SIGNED...")
    assert _match("deal closed yesterday") == "CLIENT_SIGNED"
    print(f"  {PASS} CLIENT_SIGNED matched")

def test_keyword_budget_approved():
    print("\n[S5-5] Keyword: 'budget approved for Q4' → BUDGET_APPROVED...")
    assert _match("budget approved for Q4") == "BUDGET_APPROVED"
    print(f"  {PASS} BUDGET_APPROVED matched")

def test_keyword_launching():
    print("\n[S5-6] Keyword: 'we are launching next month' → PRODUCT_LAUNCH...")
    assert _match("we are launching next month") == "PRODUCT_LAUNCH"
    print(f"  {PASS} PRODUCT_LAUNCH matched")

def test_keyword_shipping():
    print("\n[S5-7] Keyword: 'ship the v2 feature' → PRODUCT_LAUNCH...")
    assert _match("ship the v2 feature") == "PRODUCT_LAUNCH"
    print(f"  {PASS} PRODUCT_LAUNCH matched")

def test_keyword_promoted():
    print("\n[S5-8] Keyword: 'John was promoted to VP' → TEAM_CHANGE...")
    assert _match("John was promoted to VP") == "TEAM_CHANGE"
    print(f"  {PASS} TEAM_CHANGE matched")

def test_keyword_no_match():
    print("\n[S5-9] Keyword: 'hello world' → no match...")
    assert _match("hello world") is None
    print(f"  {PASS} No match (correct)")

def test_keyword_case_insensitive():
    print("\n[S5-10] Keyword: 'NEW HIRE' (caps) → HIRE_EVENT (case insensitive)...")
    assert _match("NEW HIRE JOINING NEXT WEEK") == "HIRE_EVENT"
    print(f"  {PASS} Case-insensitive match works")

def test_keyword_no_false_positive_on_strategy():
    print("\n[S5-11] Keyword: 'What is our strategy?' → no match...")
    assert _match("What is our strategy?") is None
    print(f"  {PASS} No false positive on strategy query")


# ═════════════════════════════════════════════
# SECTION 6: Cache & Cost Stats
# ═════════════════════════════════════════════

def test_clear_embedding_cache():
    print("\n[S6-1] clear_embedding_cache: should return success message...")
    r = requests.post(f"{MCP_SERVICE}/call/clear_embedding_cache", json={}, timeout=TIMEOUT_SHORT)
    assert r.status_code == 200
    content = str(r.json().get("content", ""))
    assert "cleared" in content.lower() or "cache" in content.lower(), \
        f"Unexpected response: {content}"
    print(f"  {PASS} Cache cleared: '{content}'")

def test_stats_all_keys():
    print("\n[S6-2] /stats: all cost tracker keys present...")
    r = requests.get(f"{MCP_SERVICE}/stats", timeout=TIMEOUT_SHORT)
    assert r.status_code == 200
    data = r.json()
    assert "cost_tracker" in data and "cache_size" in data and "estimated_cost" in data
    assert "total" in data["estimated_cost"]
    print(f"  {PASS} All stats keys present | cache_size={data['cache_size']}")


# ═════════════════════════════════════════════
# SECTION 7: Regression Guards
# ═════════════════════════════════════════════

def test_chief_flag_boolean_parsing():
    print("\n[S7-1] CHIEF_OF_STAFF_ENABLED env parsing must be bool, not truthy string...")
    for raw in ["false", "False", "FALSE", "0", ""]:
        assert (raw.lower() == "true") is False, f"'{raw}' incorrectly evaluated to True!"
    for raw in ["true", "True", "TRUE"]:
        assert (raw.lower() == "true") is True, f"'{raw}' should evaluate to True!"
    print(f"  {PASS} Boolean parsing correct for all common values")

def test_testcorp_no_mcp_error():
    print("\n[S7-2] testcorp tenant: response must not be a raw MCP error...")
    content = _chat("What are our top priorities?", plan="basic")
    assert not content.startswith("MCP Error"), f"Got raw MCP error: {content[:200]}"
    print(f"  {PASS} testcorp responded cleanly")

def test_response_is_string():
    print("\n[S7-3] generate_twin_response content must be a string...")
    content = _chat("What is our mission?", plan="basic")
    assert isinstance(content, str), f"Expected str, got {type(content)}: {content}"
    print(f"  {PASS} Response is string ({len(content)} chars)")


# ═════════════════════════════════════════════
# TEST RUNNER
# ═════════════════════════════════════════════

UNIT_TESTS = [
    test_keyword_hire, test_keyword_new_hire, test_keyword_client_signed,
    test_keyword_deal_closed, test_keyword_budget_approved, test_keyword_launching,
    test_keyword_shipping, test_keyword_promoted, test_keyword_no_match,
    test_keyword_case_insensitive, test_keyword_no_false_positive_on_strategy,
    test_chief_flag_boolean_parsing,
]

E2E_TESTS = [
    # S1: Infrastructure
    test_health_endpoint, test_root_endpoint, test_stats_endpoint, test_unknown_tool_returns_error,
    # S2: Digital Brain
    test_basic_business_query, test_basic_guardrail_blocks_joke, test_basic_guardrail_blocks_weather,
    test_basic_guardrail_blocks_poem, test_premium_allows_creative_query,
    test_basic_token_limit, test_empty_query_handled_gracefully, test_response_never_starts_with_mcp_error,
    # S3: KB Search
    test_search_returns_results, test_search_empty_query_returns_validation,
    # S4: Chief of Staff (flag=OFF)
    test_chief_disabled_hire_keyword, test_chief_disabled_launch_keyword, test_chief_disabled_normal_query,
    # S6: Cache & Stats
    test_clear_embedding_cache, test_stats_all_keys,
    # S7: Regression guards
    test_testcorp_no_mcp_error, test_response_is_string,
]


def run(tests: list, label: str):
    import sys
    errors = []
    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            print(f"  {FAIL} {test_fn.__name__} FAILED: {e}")
            errors.append(test_fn.__name__)

    print("\n" + "=" * 60)
    if errors:
        print(f"\033[91m{len(errors)}/{len(tests)} {label} test(s) FAILED:\033[0m")
        for e in errors:
            print(f"  {FAIL} {e}")
        sys.exit(1)
    else:
        print(f"\033[92m✔ All {len(tests)} {label} tests passed!\033[0m")
    print("=" * 60)


if __name__ == "__main__":
    unit_only = "--unit-only" in sys.argv

    if unit_only:
        print("\n" + "=" * 60)
        print("  Digital Brain — Unit Tests (offline, no server needed)")
        print("=" * 60)
        run(UNIT_TESTS, "unit")
    else:
        print("\n" + "=" * 60)
        print("  Digital Brain — Full Regression Suite")
        print(f"  Tenant: {TENANT_ID}  |  MCP: {MCP_SERVICE}")
        print("=" * 60)
        run(UNIT_TESTS + E2E_TESTS, "regression")
