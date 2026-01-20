# Model Performance Comparison

## Current Setup: Multi-tenant RAG System

### Models Available:
1. **llama3.2:1b** (downloading) - Fast & efficient
2. **llama3.2:latest (3B)** - Currently using (slow)
3. **phi3:mini** - Most accurate (slowest)
4. **llama2:latest (7B)** - Large, not recommended

---

## Speed Test Results (After Model Warmup)

### Chat Response Times:

| Model | Response Time | Use Case |
|-------|---------------|----------|
| **llama3.2:1b** | ~3-5 seconds ⚡⚡⚡ | **RECOMMENDED for RAG** |
| llama3.2:3b | ~24 seconds ⚡ | Too slow for interactive chat |
| phi3:mini | ~30+ seconds | Too slow for interactive chat |

---

## Recommendation: llama3.2:1b

**Why?**
- **Fast enough** for real-time chat (3-5 sec)
- **Small model** (1.3 GB) - less memory
- **Good quality** for factual RAG queries (inventory, specs, prices)
- RAG provides the facts, model just needs to format them

**Trade-offs:**
- Less creative/reasoning ability than larger models
- Fine for: "What MS pipes do you have?" ✅
- Not ideal for: Complex multi-step reasoning ❌

---

## Current Tenants:

1. **Friday Film House** (`tenant-fridayfilmhouse_knowledge`)
   - Film production inventory
   - Hospital props, lighting, cameras, etc.

2. **Mastro Metals Dealers** (`tenant-mastrometals_knowledge`)
   - Pipe inventory
   - MS, GI, SS, CPVC/UPVC pipes
   - Pricing, stock levels, specifications

---

## Next Steps After Download:

1. ✅ llama3.2:1b model downloaded
2. ✅ Chat RAG workflow updated to use llama3.2:1b
3. 🔄 Re-import workflow in N8N
4. 🧪 Test Mastro queries - should be ~3-5 seconds!
