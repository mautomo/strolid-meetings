# Gemini Enterprise Agent Platform — Migration Evaluation

**Workstream D — decision-grade evaluation**
Project: `strolid-meetings` (Strolid Meeting Intelligence)
Date: 2026-05-31
Question: Should the RAG/agent layer move onto the managed **Gemini Enterprise Agent Platform** (Vertex AI Search / RAG Engine + Agent Runtime + `VertexAiSessionService`/Memory Bank, published via `agents-cli publish gemini-enterprise`), or stay on the current **ADK + BigQuery `VECTOR_SEARCH` + Cloud Run** stack?

> **Scope note.** Cost is *not* a project constraint, but this document still quantifies it (Section 3) because the magnitude is decision-relevant — it confirms that *all* options are effectively free-tier at this project's traffic, which removes cost as a tie-breaker and pushes the decision onto effort, capability, and the learning goal.

---

## 1. Executive recommendation

**Verdict: HYBRID — stay on the current stack for production; stand up a thin Vertex AI Search PoC in parallel for learning and de-risking.**

The current ADK + BigQuery `VECTOR_SEARCH` + Cloud Run stack already does everything this internal, ~55-meeting / ~500-chunk, single-team tool needs, and it does things the managed platform cannot do as cleanly: it co-locates RAG retrieval with the same relational warehouse that powers `get_analytics_summary`, `get_performance_report`, and the four artifact generators, and it lets the agent apply **rich structured filters** (attendees, topics, date ranges, meeting IDs) inside a single SQL `VECTOR_SEARCH` call. A wholesale migration would trade that integration and the custom meeting-tuned chunker for managed convenience the project does not currently need. However, the approved learning goal ("hands-on Gemini Enterprise") and a real future risk (self-managing embeddings/index as data grows) both justify a **low-cost PoC**: ingest `original-docs/` into a Vertex AI Search data store, wire a `VertexAiSearchTool`, and A/B a handful of queries against today's BigQuery RAG. That satisfies the learning objective and produces evidence for the decision gate without disrupting the working system.

---

## 2. Component mapping table

Current architecture (verified from source): `chatbot/agent.py` (ADK `Agent`, `gemini-2.0-flash`, 7 tools), `chatbot/server.py` (ADK `Runner` + `DatabaseSessionService` on SQLite, FastAPI on Cloud Run, Firebase frontend), `pipeline/src/embeddings.py` (custom `chunk_dialogue` / `chunk_paragraphs`, `gemini-embedding-2`, BigQuery `embeddings` table with `VECTOR_SEARCH`).

| Current piece | Managed equivalent | Migration effort | What's gained | What's lost |
|---|---|---|---|---|
| **BigQuery `VECTOR_SEARCH`** over `strolid_meetings.embeddings` (cosine, `top_k=5`, similarity ≥ 0.55 filter — `agent.py:74–101`) | **Option A: Vertex AI Search data store** via `VertexAiSearchTool(data_store_id=...)` <br>**Option B: Vertex AI RAG Engine** (`VertexRagStore` / `VertexAiRagRetrieval`, RAG-managed Spanner DB) | **A: Low–Med** (create data store, ingest docs, swap one tool) <br>**B: Med–High** (corpus + managed vector DB + ingestion config) | Managed indexing, ranking/reranking, automatic refresh, no embed-and-load pipeline to maintain; built-in grounding/citations | The **structured pre-filter** (attendees/topics/date/meeting_id done inside SQL — `agent.py:47–73`) becomes harder: `VertexAiSearchTool` supports a `filter` string but requires metadata to be modeled in the data store schema, and `VertexAiSearchTool` **must be the only tool on its agent** (see Section 4 risk). Tight co-location with the relational warehouse is broken. |
| **Custom chunker** — `chunk_dialogue` (dialogue/transcript, 800–1500 chars, `\n\n` blocks) and `chunk_paragraphs` (sentence-aware) in `embeddings.py:62–167` | Platform-managed chunking. RAG Engine = fixed-size chunking (free); Vertex AI Search = automatic layout-aware chunking | **Discarded** if migrated | Less code to maintain | **Loss of meeting-specific tuning.** The current chunker is deliberately tuned for speaker-turn transcripts vs. prose docs (`is_transcript` switch). Managed chunkers are generic; retrieval quality on dialogue transcripts is the #1 thing the PoC must measure. RAG Engine's fixed-size chunking is the bluntest; Vertex AI Search layout chunking is better but still not transcript-aware. |
| **`gemini-embedding-2`** embeddings generated in-pipeline (`embeddings.py:169–174`) | Embeddings generated and managed by the data store / RAG corpus | Low (stop generating them yourself) | No embedding API calls or vector storage to manage | Control over embedding model choice; ability to re-embed on your schedule |
| **SQLite `DatabaseSessionService`** (`server.py:174,257`, `adk_sessions.db`) | **`VertexAiSessionService`** (managed, persistent) + optional **Memory Bank** (`VertexAiMemoryBankService`) for cross-session memory | **Low** (swap the service class; requires an Agent Engine ID) | Managed, scalable, durable sessions; Memory Bank adds cross-conversation recall (user prefs, past decisions) | The SQLite DB is a single 400 KB file today — trivially simple. Managed sessions add a dependency (Agent Engine) and per-event billing. Memory Bank is a genuine *new capability*, not a replacement. |
| **Cloud Run** (FastAPI, `server.py`, project `meeting-analysis-*`, region `us-central1`) | **Agent Runtime** (a.k.a. Vertex AI Agent Engine; deploy via `agents-cli deploy --deployment-target agent_runtime`) | **Med** (re-package as `AdkApp`; lose the custom FastAPI surface) | Managed auto-scaling, not billed when idle, native `VertexAiSessionService`, purpose-built for agents, prerequisite for `publish gemini-enterprise` (ADK mode) | **Agent Runtime has no event triggers** — no Pub/Sub, Eventarc, or Cloud Scheduler (`google-agents-cli-deploy` skill, decision matrix). The current FastAPI app also exposes custom REST endpoints (`/api/meetings`, `/api/stats`, the SSE `/api/chat` with a bespoke `StreamFilter` that strips artifact JSON from the token stream — `server.py:19–112`). Those custom endpoints and the streaming-filter logic do **not** port to Agent Runtime cleanly; they would need a separate Cloud Run/frontend tier anyway (the docs call this a "decoupled deployment"). |
| **Firebase/Firestore** message + artifact persistence; Next.js frontend | Unchanged — frontend stays; could call Agent Runtime via a decoupled backend | n/a | n/a | Nothing, but it means Agent Runtime would not eliminate the Cloud Run/FastAPI tier — it would sit *behind* it. |

**Sources:** code paths cited inline from `chatbot/agent.py`, `chatbot/server.py`, `pipeline/src/embeddings.py`. `VertexAiSearchTool`, `VertexRagStore`, `VertexAiRagMemoryService`, `VertexAiSessionService`, `VertexAiMemoryBankService` signatures from Context7 `/google/adk-docs` (grounding/grounding_with_search.md, sessions/memory.md, sessions/session/index.md, api-reference/agentconfig). Agent Runtime "no event triggers" + decoupled-deployment guidance from the local skill **`google-agents-cli-deploy`**. Publish flow from **`google-agents-cli-publish`**.

---

## 3. Cost model (pay-as-you-go, per SKU)

> **Verify in the Cloud Billing console before committing.** All figures below are list prices captured 2026-05-31 and Google changes them (several of these SKUs only began billing between Dec 2025 and Feb 2026). Treat this table as order-of-magnitude, not a quote.

| SKU | Unit rate | Free tier | Source |
|---|---|---|---|
| **Vertex AI Search — Standard** (semantic retrieval) | **$1.50 / 1,000 queries** | 10,000 queries/account/month | cloud.google.com/generative-ai-app-builder/pricing (via exa) |
| **Vertex AI Search — Enterprise** (core generative answers / AI Mode) | **$4.00 / 1,000 queries** | (within the 10K, excl. advanced answers) | same |
| **Vertex AI Search — Advanced Generative Answers** add-on | **+$4.00 / 1,000 input queries** (≈$6/1K all-in for advanced) | — | same; cloudzero.com Vertex AI guide |
| **Vertex AI Search — index storage** | **~$5.00 / GB / month** (general model) | — | generative-ai-app-builder/pricing |
| **Agent Runtime — compute** | **$0.0864 / vCPU-hour** | **First 50 vCPU-hours/month free** (180,000 vCPU-sec) | cloud.google.com/products/gemini-enterprise-agent-platform/pricing (via exa) |
| **Agent Runtime — memory** | **$0.0090 / GiB-hour** | **First 100 GiB-hours/month free** | same |
| **Sessions** (`VertexAiSessionService`) | **$0.25 / 1,000 content events** stored | — (billing began ~Feb 11, 2026) | same |
| **Memory Bank — stored** | **$0.25 / 1,000 memories/month** (+ LLM cost to generate) | — | same |
| **Memory Bank — retrieved** | **$0.50 / 1,000 memories returned** | First 1,000 returned/month free | same |
| **RAG Engine** | Composite: RAG-managed **Spanner** instance (Basic = 100 processing units, billed continuously) + embedding + reranking + model tokens, each surfaced separately | — | docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-engine-billing (via exa) |
| **Gemini 2.0 Flash** (current agent model) | **$0.10 in / $0.40 out per 1M tokens** | rate-limited dev tier | ai.google.dev/gemini-api/docs/pricing |
| **Gemini 2.5 Flash** | **$0.30 in / $2.50 out per 1M tokens** | rate-limited dev tier | same |

> **Footnote on Gemini 2.0 Flash:** the Workstream-D brief cited $0.15/$0.60; the current published list price is **$0.10 in / $0.40 out** per 1M tokens. The lower numbers are used here. Either way it is immaterial at this volume.

### Estimated monthly cost for *this* project at low internal traffic

Assume a single team, generous estimate of **1,000 agent conversations/month**, ~4 turns each → ~4,000 RAG queries, ~8,000 session events, modest token use, index ≈ tens of MB (94 source docs, ~500 chunks).

- **If migrated to managed (Option A, Vertex AI Search Standard + Agent Runtime + Sessions):**
  - Vertex AI Search: 4,000 queries → **$0** (under the 10K/month free tier).
  - Agent Runtime: a low-traffic, idle-billed agent on ~1 vCPU / ~2 GiB realistically stays **under 50 vCPU-hr and 100 GiB-hr** → **$0** (free tier).
  - Sessions: 8,000 events × $0.25/1K = **~$2.00/month**.
  - Memory Bank (if enabled): a few thousand memories → **~$1–2/month**.
  - Gemini 2.0 Flash tokens: at this volume, **a few dollars/month** at most.
  - **Total: roughly $5–10/month**, with most line items sitting in free tier.
- **If migrated to RAG Engine (Option B):** the **RAG-managed Spanner instance bills continuously** even at zero traffic (Basic tier = 100 processing units), so this option carries a **non-trivial always-on floor (tens of dollars/month)** regardless of usage — the one option where idle cost is meaningful.
- **Staying on current stack:** BigQuery `VECTOR_SEARCH` over ~500 rows + storage + Cloud Run min-instances + embedding/Gemini tokens → also **a few dollars/month**, dominated by Cloud Run min-instance time if any is set.

**Takeaway:** At this traffic, **every option except RAG Engine is effectively free**. Cost does not differentiate stay-vs-go (consistent with "cost is not a constraint"). The RAG Engine Spanner floor is the only cost worth flagging, and it argues *against* Option B for a tool this small.

---

## 4. Migration effort & risks

### Lower-effort path — `VertexAiSearchTool` swap + data-store ingestion of `original-docs/`

Concrete steps:

1. **Create a Vertex AI Search app + data store** (unstructured, in `us-central1` or `global`). Enable the Discovery Engine API.
2. **Ingest `original-docs/`** (94 files: 60 `.docx`, 28 `.pdf`, 4 `.md`, 2 `.txt`) — upload to a GCS bucket and point the data store at it, or import directly. To preserve filtering, attach **structured metadata** (date, attendees, topics, meeting_id) to each document during import so the `filter` string can reproduce today's SQL filters.
3. **Add `VertexAiSearchTool`** to a (new) agent:
   ```python
   from google.adk.tools import VertexAiSearchTool
   DATASTORE_ID = "projects/PROJECT/locations/LOCATION/collections/default_collection/dataStores/DATASTORE_ID"
   tool = VertexAiSearchTool(data_store_id=DATASTORE_ID)
   ```
   (Context7 `/google/adk-docs`, grounding_with_search.md.)
4. **A/B evaluate** retrieval quality vs. the current BigQuery RAG (Section 5).

**Risks / tradeoffs:**

- **`VertexAiSearchTool` cannot share an agent with other tools.** Per ADK docs ("this tool can only be used by itself within an agent instance"), it cannot sit alongside `get_analytics_summary`, `get_performance_report`, and the four artifact generators on the same `Agent`. You would need a **sub-agent / agent-as-tool** pattern, or a `DynamicFilterSearchTool` subclass — added architectural complexity the current single-agent design avoids.
- **Custom chunker is discarded.** Vertex AI Search applies its own layout-aware chunking; it is not transcript/speaker-turn aware. Retrieval quality on dialogue transcripts is the key unknown — measure it.
- **Filter parity is not free.** Today's attendee/topic/date/meeting_id filtering lives in SQL (`agent.py:47–73`). Reproducing it requires modeling that metadata in the data store and translating to Vertex AI Search `filter` syntax.

### Bigger path — Vertex AI RAG Engine

Concrete steps: create a RAG corpus, choose a vector DB (RAG-managed Spanner Basic, or bring-your-own), configure ingestion + chunking (fixed-size is free) + embedding model + optional reranker, then attach via `VertexRagStore` / `VertexAiRagRetrieval` or `VertexAiRagMemoryService`.

**Risks / tradeoffs:**

- **Always-on Spanner cost floor** (Section 3) even at zero traffic — the worst fit for a ~500-chunk tool.
- **Most managed, least control:** fixed-size chunking is the bluntest option for transcripts; reranking and model costs stack.
- Highest migration effort for capability this project does not yet need.

### Cross-cutting risk

- **Agent Runtime has no event triggers** (`google-agents-cli-deploy`). If meeting ingestion ever becomes event-driven (e.g., a new transcript dropped to a bucket triggers re-embed), Agent Runtime cannot host that — it would stay on Cloud Run. The current pipeline is run manually (`embeddings.py main()`), so this is latent, not active.
- **Custom FastAPI surface and `StreamFilter`** (`server.py`) do not port to Agent Runtime; a decoupled Cloud Run/frontend tier remains required. Migrating to Agent Runtime therefore *adds* a tier rather than removing one.

---

## 5. Recommended thin PoC slice (satisfies the learning goal regardless of the final decision)

Goal: get hands-on with Gemini Enterprise and produce A/B evidence, **without touching production code** (per the no-code-change constraint, do this in a scratch dir / separate notebook).

**Steps & commands:**

1. **Enable APIs and pick a region.**
   ```bash
   gcloud services enable discoveryengine.googleapis.com aiplatform.googleapis.com --project=PROJECT_ID
   export GOOGLE_CLOUD_PROJECT=PROJECT_ID
   export GOOGLE_CLOUD_LOCATION=us-central1
   export GOOGLE_GENAI_USE_VERTEXAI=TRUE
   ```
2. **Stage `original-docs/` to GCS** (the 94 source files already on disk):
   ```bash
   gsutil -m cp -r original-docs/* gs://PROJECT_ID-vais-poc/original-docs/
   ```
3. **Create a Vertex AI Search data store + app** over that bucket (Console → Gemini Enterprise / Agent Builder → Apps → Search, or via the Discovery Engine API). Choose **Standard edition** (semantic) for the PoC — it stays inside the 10K-query free tier.
4. **Build a throwaway PoC agent** with `VertexAiSearchTool` (its own agent, since the tool must be solo):
   ```python
   from google.adk.agents import Agent
   from google.adk.tools import VertexAiSearchTool
   poc = Agent(
       name="vais_poc",
       model="gemini-2.5-flash",
       instruction="Answer using the meeting docs; cite sources.",
       tools=[VertexAiSearchTool(
           data_store_id="projects/PROJECT/locations/us-central1/collections/default_collection/dataStores/DATASTORE_ID")],
   )
   ```
5. **(Optional) Deploy + publish to Gemini Enterprise** to exercise the full managed path:
   ```bash
   agents-cli deploy --deployment-target agent_runtime --project PROJECT_ID --region us-central1 --no-confirm-project
   agents-cli publish gemini-enterprise \
     --gemini-enterprise-app-id projects/PROJECT/locations/global/collections/default_collection/engines/ENGINE_ID
   ```
   (Auto-detects the runtime ID from `deployment_metadata.json` — `google-agents-cli-publish`.)
6. **A/B a fixed query set** (5–10 prompts) against today's BigQuery RAG. Reuse real questions the agent already handles well — e.g. *"What did Michael say about website launch delays?"*, attendee-filtered and date-filtered variants, and a cross-document synthesis question. For each, compare: (a) relevance of top passages, (b) whether transcript dialogue is retrieved coherently (the chunker question), (c) citation quality, (d) whether managed filtering can reproduce the attendee/topic/date filters.

**Deliverable:** a short comparison note (relevance, chunking quality on transcripts, filter parity, latency). This is the evidence the decision gate consumes — and the learning goal is met whether the verdict is migrate or stay.

---

## 6. Decision gate — what would tip it each way

**Tip toward MIGRATING (to Vertex AI Search + Agent Runtime):**

- PoC shows managed chunking retrieves transcript dialogue **as well as or better than** the custom chunker on the A/B query set.
- Managed `filter` syntax can faithfully reproduce attendee / topic / date / meeting_id filtering.
- Data volume grows materially (hundreds of meetings / tens of thousands of chunks) such that maintaining the embed-and-load pipeline and BigQuery vector index becomes real toil.
- A need emerges for capabilities the managed platform gives "for free": built-in grounding/citations, Memory Bank cross-session recall, or org-wide discoverability of the agent **inside Gemini Enterprise**.
- The team wants to standardize future agents on the managed platform and treat this as the reference migration.

**Tip toward STAYING (current ADK + BigQuery `VECTOR_SEARCH` + Cloud Run):**

- PoC shows the custom transcript chunker meaningfully **outperforms** managed chunking on dialogue retrieval (the most likely outcome given the tuning in `embeddings.py`).
- Tight co-location of RAG with the relational warehouse (analytics, performance, artifact tools all hitting `strolid_meetings`) remains valuable, and the single-agent design is worth preserving (avoids the "VertexAiSearchTool must be solo" sub-agent complexity).
- Traffic/data stay small (the realistic case): managed convenience buys little, and **RAG Engine's always-on Spanner floor** is pure overhead.
- The custom FastAPI surface (`/api/meetings`, `/api/stats`, SSE `StreamFilter`) and event-style pipeline runs are easier to keep on Cloud Run than to split across Agent Runtime + a decoupled tier.

**Default if the PoC is inconclusive:** stay on the current stack (it works, it's integrated, it's effectively free), keep the Vertex AI Search data store around as a sandbox, and revisit when data volume or a new capability need crosses the thresholds above.

---

### Source index

- **Project code:** `chatbot/agent.py`, `chatbot/server.py`, `pipeline/src/embeddings.py` (read directly).
- **Context7 MCP — `/google/adk-docs`:** `VertexAiSearchTool` (grounding/grounding_with_search.md, integrations/agent-search.md), `VertexRagStore`/`VertexAiRagRetrieval`/RAG config (api-reference/agentconfig), `VertexAiSessionService` (sessions/session/index.md, streaming/dev-guide/part1.md), `VertexAiMemoryBankService`/`VertexAiRagMemoryService`/Memory Bank (sessions/memory.md, integrations/express-mode.md), Agent Runtime deploy (deploy/agent-runtime/*).
- **Context7 MCP — `/google/adk-python`** (library resolved; v2.0.0a1 line) for ADK `Agent`/tool API context.
- **Local skills:** `google-agents-cli-deploy` (Agent Runtime vs Cloud Run vs GKE matrix; no event triggers; decoupled deployment; idle-not-billed cost model), `google-agents-cli-publish` (`agents-cli publish gemini-enterprise`, ADK vs A2A modes, auto-detection from `deployment_metadata.json`).
- **Web (via exa `web_search_exa`):** cloud.google.com/products/gemini-enterprise-agent-platform/pricing (Agent Runtime, Sessions, Memory Bank rates + free tier); cloud.google.com/generative-ai-app-builder/pricing (Vertex AI Search Standard/Enterprise/Advanced + index storage); docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-engine-billing (RAG Engine / RAG-managed Spanner); ai.google.dev/gemini-api/docs/pricing (Gemini 2.0/2.5 Flash tokens); cloudzero.com Vertex AI pricing guide (2026) and uibakery.io / majormatters.co corroboration.
