# RAG System Test Queries - Quick Reference

## 🎯 **Test via OpenWebUI Chat**

Login at: **http://localhost:3000**

---

## **Quick Test Queries:**

### 1. **Simple Fact** ⭐
```
What is our revenue?
```
**Expected:**  
- TechCorp: "$50,000,000"
- DemoTech: "$2,500,000"

---

### 2. **Multiple Facts**
```
What are our key financial metrics?
```
**Expected:** Revenue, profit, expenses with numbers

---

### 3. **Employee Count**
```
How many employees do we have?
```
**Expected:**
- TechCorp: "450 employees"
- DemoTech: "35 employees"

---

### 4. **Strategic Info**
```
What are our top 3 projects?
```
**Expected:** List with project names and values

---

### 5. **Calculations**
```
What is our profit margin?
```
**Expected:** "28%" (for DemoTech) or calculated value

---

### 6. **Negative Test** (Should fail gracefully)
```
What is our stock price?
```
**Expected:** "I don't have information about stock price"

---

### 7. **Tenant Isolation Test** ⭐⭐⭐
**Step 1:** Login as `alice.tenanta@gmail.com`
```
What is our revenue?
```
**Should get:** "$50,000,000"

**Step 2:** Logout, login as `demo.demotenant@gmail.com`
```
What is our revenue?
```
**Should get:** "$2,500,000" (DIFFERENT!)

---

### 8. **Complex Query**
```
Compare our revenue, profit, and employee count
```
**Expected:** All three metrics together

---

### 9. **Abbreviation**
```
What's our EBITDA?
```
**Expected:** Should find EBITDA value from financial data

---

### 10. **Follow-up** (Tests conversation memory)
```
1st: What is our revenue?
2nd: How does that compare to expenses?
```
**Expected:** Should reference revenue from first question

---

## **Scoring:**

✅ = Perfect answer with exact numbers  
⚠️ = Partial - got some info but incomplete  
❌ = Failed - wrong or no answer  

**Your Score: __ / 10**

- **9-10**: Excellent! (85-100%)
- **7-8**: Good (70-85%)
- **5-6**: Fair - needs optimization (50-70%)
- **<5**: Poor - definitely needs hybrid approach!

---

## **Common Issues & Fixes:**

### Issue: "I can't provide confidential information"
**Fix:** Apply better system prompt (Optimization #4 & #5)

### Issue: Answers are vague/generic
**Fix:** Increase context size (Optimization #6)

### Issue: Missing relevant info
**Fix:** Retrieve more docs + rerank (Optimizations #2 & #3)

### Issue: Wrong answers
**Fix:** Query enhancement (Optimization #1)

### Issue: Different tenants see same data
**Fix:** Check tenant/persona filters in Qdrant

---

## **After Testing:**

1. **Count your score**
2. **Note which queries failed**
3. **Apply hybrid optimizations** from docs
4. **Re-test**
5. **Compare before/after scores**

**Expected improvement:** +3 to +4 points (30-40%)

---

## **API Testing (Command Line):**

```bash
# Test as TechCorp CEO
curl -X POST http://localhost:5678/webhook/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is our revenue?",
    "tenantId": "tenant-tenanta",
    "personaId": "CEO"
  }'

# Test as DemoTech CEO
curl -X POST http://localhost:5678/webhook/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is our revenue?",
    "tenantId": "tenant-demotenant",
    "personaId": "CEO"
  }'
```

Should return different answers!
