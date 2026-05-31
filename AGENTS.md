# Working in this repo

Conventions and gotchas for anyone (human or agent) making changes here. See `README.md` for the architecture overview.

## Layout & ownership

- `pipeline/` — offline batch (extract → normalize → warehouse → embed → verify). Pure Python, talks to BigQuery + Gemini. No web server.
- `chatbot/` — the runtime: `agent.py` (ADK agent + tools), `server.py` (FastAPI + ADK Runner + streaming endpoint).
- `frontend/` — Next.js 16 app. **Has its own `frontend/AGENTS.md` — read it before editing frontend code. This is NOT the Next.js in your training data; read `frontend/node_modules/next/dist/docs/` for current APIs.**

## Environment & config

- Python 3.11+. Dependencies in `pyproject.toml`, managed with `uv` (`uv sync`). The Dockerfile pins Python 3.11-slim and `pip install .`.
- GCP project IDs are read from `GOOGLE_CLOUD_PROJECT` (defaults to `meeting-analysis-496916` in code); Firebase/Cloud Run live in `meeting-analysis-6c116`. Auth via Application Default Credentials. `GEMINI_API_KEY` from env.
- BigQuery dataset: `strolid_meetings`.

## ADK conventions (important — these are the source of past bugs)

- **Models:** agent runs `gemini-2.0-flash`; extraction uses `gemini-2.5-flash`; embeddings use `gemini-embedding-2`. **Do not change a `model=` value unless explicitly asked** — a Gemini 404 is almost always a location/credentials issue, not a wrong model name.
- **Tools return dicts, not JSON strings.** ADK function tools should return JSON-serializable dicts (convention `{"status": "success", ...}`). The artifact generators historically returned `json.dumps(...)` strings, which forced the server to re-parse and scrape text — avoid that pattern.
- **Stream ADK events; never scrape JSON out of model text.** `Runner.run_async` yields structured `Event`s:
  - `event.partial` + `event.content.parts[0].text` → incremental token deltas
  - `event.is_final_response()` → the final displayable text
  - `event.get_function_calls()` → tool calls (`.args` is a dict)
  - `event.get_function_responses()` → tool results (`.response` is a dict) — this is how artifact payloads arrive cleanly
  - `event.actions.skip_summarization` → raw tool result should be shown directly
  This is Google's canonical pattern (confirmed via Context7 `/google/adk-python`). It replaces any brace-counting / `StreamFilter` text parsing.
- **Sessions:** currently `DatabaseSessionService` (SQLite, `adk_sessions.db`). The managed equivalent is `VertexAiSessionService` (Agent Runtime) — relevant only if migrating to Gemini Enterprise.

## Docs / library lookups

Context7 is wired via the Docker MCP gateway (`.mcp.json` → `MCP_DOCKER`, profile `dev`). Prefer it for current library docs: `mcp__MCP_DOCKER__resolve-library-id` → `mcp__MCP_DOCKER__get-library-docs`. ADK docs: `/google/adk-python`, `/google/adk-docs`. The local `google-agents-cli-*` skills are the authoritative per-task ADK reference.

## Testing & linting

- `pytest` for tests, `ruff check` for lint. Run both before claiming a change is complete.
- For RAG/retrieval changes, run `python pipeline/src/verify_rag.py` and compare results before/after.
- For UI/stream changes, run the backend + `npm run dev` and exercise a normal chat, each artifact type, and a forced error.

## Deploy

`./deploy_all.ps1` (frontend → Firebase Hosting/Firestore, backend → Cloud Run in `meeting-analysis-6c116`/`us-central1`). Don't deploy without explicit approval.
