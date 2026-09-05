# Digital Brain — Data Quality Guide

> **Goal:** Help your Digital Brain give precise, confident, grounded answers.
> The brain can only know what you've uploaded. This guide tells you how to upload well.

---

## How it works (in plain terms)

```
Your file (PDF / DOCX / XLSX / TXT / PPTX)
        ↓
  Parsed into plain text
        ↓
  Split into ~2000-character chunks (with 300-char overlap)
        ↓
  Each chunk embedded as a vector → stored in Qdrant
  (isolated per tenant + persona)
        ↓
  At query time: top matching chunks retrieved → fed to LLM
```

**Key implication:** The brain answers from chunks, not the full document.
A poorly written chunk = a poorly grounded answer.

---

## Step 1 — Choose the right file format

| Format | Quality | Notes |
|---|---|---|
| `.txt` / `.md` | ⭐⭐⭐⭐⭐ Best | Zero parsing loss. Recommended. |
| `.docx` | ⭐⭐⭐⭐ Great | Paragraphs and tables both extracted |
| `.pdf` (text-based) | ⭐⭐⭐ Good | Text extracted page by page |
| `.xlsx` / `.csv` | ⭐⭐⭐ Good | Each sheet ingested separately |
| `.pptx` | ⭐⭐ OK | Slide text only — no images or diagrams |
| `.pdf` (scanned/image) | ❌ Fails | No OCR — returns empty, do not upload |
| `.ppt` (old format) | ❌ Fails | Not supported. Convert to `.pptx` first |

> **Tip:** If you have a scanned PDF, run it through Adobe Acrobat's "Make Searchable" or Google Docs OCR before uploading.

---

## Step 2 — Structure your documents well

The brain chunks at **2,000 characters with 300-character overlap**.
A key fact that spans two chunk boundaries may be split.

### ✅ Do this

- **Use headings** — they anchor chunks to topics
  ```
  ## Q3 2024 Growth Strategy
  ## Leave Policy — Effective Jan 2025
  ## Onboarding Process for Enterprise Clients
  ```

- **Write in complete sentences with full context**
  ```
  ✅ "In Q3 2024, we decided to pause EMEA expansion because we lacked
      a local anchor hire and the pipeline did not justify the cost."

  ❌ "EMEA — paused. No anchor. Pipeline weak."
  ```

- **Keep decisions + rationale together** — don't split a decision across pages

- **Define acronyms in the same document**
  ```
  ✅ "AVT (Average Transaction Value) is calculated as..."
  ❌ "AVT is our primary growth lever"  ← no definition = brain can't explain it
  ```

- **Use Q&A format for FAQ content** — retrieves perfectly
  ```
  Q: What is our standard payment term for enterprise clients?
  A: Net 30 from invoice date. Exceptions require CFO approval.
  ```

### ❌ Avoid this

- Bullet-only documents with no surrounding sentence context
- Tables as the only format for critical decisions
- Very long documents (50+ pages) without section headers
- Acronyms with no definitions anywhere in the file
- Splitting related facts across multiple short files

---

## Step 3 — Upload to the correct persona

The brain is **persona-isolated**. CEO's documents are stored separately from HR's.
Uploading to the wrong persona means that persona won't find the knowledge.

**S3 key format:**
```
tenant-{tenantId}/{personaId}/your-filename.pdf

Examples:
  tenant-peakpa/ceo/strategic-outlook-2024.pdf
  tenant-peakpa/hr/leave-policy-2025.docx
  tenant-peakpa/finance/q3-cashflow-analysis.xlsx
  tenant-peakpa/coach/peak-coaching-framework.pdf
```

**Persona mapping:**

| Persona ID | What to upload |
|---|---|
| `ceo` | Strategy docs, board minutes, vision statements, key decisions |
| `hr` | Policies, onboarding guides, org charts, people processes |
| `finance` | Financial reports, cashflow trackers, budget frameworks |
| `sales` | Playbooks, pitch decks, ICP definitions, win/loss analysis |
| `coach` | Coaching frameworks, methodologies, scoring systems |
| `admin` | SOPs, operations manuals, vendor agreements |

---

## Step 4 — Verify ingestion after upload

After uploading, always test with a question answerable directly from the doc.

**Via curl:**
```bash
curl -X POST http://<your-mcp-url>/call/search_knowledge_base \
  -H "Content-Type: application/json" \
  -d '{
    "query": "paste a key phrase from your doc here",
    "tenantId": "your-tenant-id",
    "personaId": "ceo"
  }'
```

**What to check:**
- `results` array contains chunks from your uploaded file
- Chunk text is readable and contextually complete
- If `results` is empty → ingestion failed or wrong persona

---

## Step 5 — Best document types by use case

| What the brain needs to do | Best document type |
|---|---|
| Answer strategy questions | Strategy memos, decision logs, leadership notes |
| Walk through a process | SOPs, playbooks, step-by-step guides |
| Explain a framework | Methodology docs with named components |
| Quote specific numbers | Scorecards, KPI trackers, financial summaries |
| Answer role-specific questions | Documents written by or for that persona |
| Handle FAQs fluently | Literal Q&A documents |

---

## Step 6 — What NOT to upload

| ❌ Don't upload | Why |
|---|---|
| Generic internet articles / blog posts | Adds noise — brain already has general knowledge |
| Scanned image PDFs | No text extracted — wastes an upload |
| Duplicate files | Creates redundant chunks, degrades retrieval ranking |
| Unfilled templates | Brain surfaces placeholder data as real answers |
| Superseded / outdated documents | Brain cannot know what's old — presents all docs as current |
| Documents from another persona's domain | Causes cross-contamination in responses |

---

## Step 7 — Pre-upload quality checklist

```
□ Is this a text-based PDF (not scanned)?
□ Does the document have clear section headings?
□ Are key facts in complete sentences with full context?
□ Are all acronyms defined somewhere in the same file?
□ Am I uploading to the correct persona?
□ Is the content current and not superseded by a newer version?
□ Have I removed placeholder / unfilled sections?
□ Is this document relevant to what users will actually ask?
```

---

## Step 8 — Ongoing maintenance

| Action | When |
|---|---|
| Re-upload updated documents | Whenever a policy, strategy, or process changes |
| Clear stale knowledge | Use `clear_tenant_knowledge` API before re-uploading a fully revised doc |
| Test after every batch upload | Run 3–5 representative queries and check responses |
| Review knowledge gaps | If brain says "not in my records" frequently, identify missing docs |

---

## File size recommendations

| File type | Recommended max |
|---|---|
| PDF | 50 pages / ~5MB |
| DOCX | Split at 100+ pages |
| XLSX | Split sheets with 500+ rows into separate files |
| TXT / MD | No limit |
| PPTX | 50 slides recommended |

> **For large documents:** Split into topic-focused sub-documents.
> A 10-page focused doc retrieves better than a 100-page mixed doc.

---

## Example — ideal CEO knowledge base

```
tenant-peakpa/ceo/
├── strategic-direction-2025.md        ← Where we're going and why
├── key-decisions-log.md               ← Decision + rationale, chronological
├── growth-priorities-q3.md            ← Current quarter focus
├── emea-expansion-analysis.md         ← One topic, one file
├── core-values-and-culture.md         ← Company identity
├── board-update-aug-2025.txt          ← Specific communication
└── faq-ceo-perspective.md             ← Q&A format for common questions
```

Each file = one focused topic. No monolithic "everything" document.

---

*Last updated: September 2025*
*For ingestion issues, check MCP server logs via SSM session.*
