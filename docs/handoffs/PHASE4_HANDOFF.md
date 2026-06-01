# Handoff: Strolid Meetings UI rebuild — resuming at Phase 4 (DeepThink)

This is a session handoff written before a `/clear`. It captures current state and everything needed to start Phase 4 cold. Companion docs: approved plan at `C:\Users\teamb\.claude\plans\drifting-tickling-squid.md`; auto-memory at the project memory dir (`project_ui_redesign_roadmap.md`).

## Where things stand

- Branch `dev`, commit `30313b2`. Open PR **#3** (dev -> main): "feat: Vandoko-brand UI rebuild, tool drawer, admin allowlist, private conversations". Not yet merged.
- Phases 1, 2, 3, 3.5 are DONE and verified locally (frontend `npm run build` static export + `npm run lint` clean; `chatbot/server.py` compiles; routes live).
- Firestore rules `frontend/firestore.rules` are DEPLOYED to `meeting-analysis-6c116`.
- NOT deployed: Firebase Hosting (web app) and Cloud Run backend still run the OLD build. All new work verified on localhost only. `./deploy_all.ps1` is approval-gated.

## Running environment (may persist across /clear)

- Backend runs as a background process on `http://localhost:8000`, launched WITHOUT `--reload`, so any `server.py` edit needs a restart. Launch command (from repo root):
  `ADMIN_EMAILS="mdonovan@vandoko.ai" ./.venv/Scripts/python.exe -m uvicorn server:app --app-dir chatbot --host 0.0.0.0 --port 8000`
  To restart: find PID with `netstat -ano | grep LISTENING | grep ':8000'`, then `taskkill //F //PID <pid>`, then relaunch (use run_in_background). The startup log prints `[access] ADMIN_EMAILS=... ALLOWLIST_ENFORCED=...`.
- Frontend dev server is the USER's (`npm run dev`), typically on `localhost:3001` (hot-reloads). Do not spawn competing dev servers.
- Tooling gotchas: `ruff` is NOT installed and not pinned in pyproject — use `python -m py_compile chatbot/server.py` as the backend gate. PowerShell invocation via Bash is DENIED by the sandbox; use `taskkill`/`netstat` directly. Force-push and resetting shared branches is denied.
- User signs in as `mdonovan@vandoko.ai` (GCP/Firebase owner). `ALLOWLIST_ENFORCED` is currently off (access not gated; conversations are still private via ownership rules).

## Architecture quick map

- `pipeline/` offline batch (BigQuery + Gemini). `chatbot/agent.py` (ADK agent + tools), `chatbot/server.py` (FastAPI + SSE). `frontend/` Next.js 16 static export SPA (no Next API routes; all endpoints on FastAPI).
- Frontend: `src/context/ChatContext.tsx` holds all state (auth, role, conversations, scope, tool-drawer, streaming). `src/lib/{api,types,firebase}.ts`. Components under `src/components/{auth,shell,chat,chat/tools,canvas,canvas/artifacts,admin,common}`.
- Conversations: `conversations/{id}` doc (ownerUid, ownerEmail, title, sharedWith[], scope) + `messages` subcollection. `session_id` in the chat request IS the conversation id. Messages read client-side via onSnapshot, gated by `firestore.rules`. All writes via backend Admin SDK.
- Artifacts: backend tools return dicts `{artifact_type, ...}`; server.py `ARTIFACT_TOOLS` set + `_ARTIFACT_MODELS` validate before SSE emit; `CANVAS_HINTS` maps a canvas pick to a generator. Frontend renders per type in `components/canvas/artifacts/*` selected by `Canvas.tsx`.
- ADK rules (do not violate): never change a `model=` value (agent uses `gemini-2.0-flash`, extraction `gemini-2.5-flash`, embeddings `gemini-embedding-2`); tools return dicts not JSON strings; stream events, never scrape model text.
- Brand rules (hard): no emojis, no em dashes; semantic colored Lucide icons for alerts. Tokens in `frontend/src/app/globals.css`; source of truth `docs/brand/vandoko-brand-guidelines.html`.

## Pending verification (carry forward)

- In-browser end-to-end of Phase 3.5 after the rules deploy: new chat creates a private conversation, history lists owned + shared, share read-only works, sharee sees it read-only and cannot see other private chats. (User was testing on localhost:3001.)
- Optional: enable `ALLOWLIST_ENFORCED=true` and confirm gating.

## Phase 4: DeepThink (per-person direction reversals + new artifact)

Goal (locked with user): find a direction an individual set, who set it, and detect the SAME individual later reversing it. Render as a NEW artifact type. The pipeline already has ~80% of the data.

What exists:
- `decisions` table: `decision_id`, `description`, `decided_by` (REPEATED STRING), `meeting_id`, `meeting_date` (DATE), `topic`, `confidence` (firm|tentative|exploratory), `supersedes`, `superseded_by`.
- `direction_changes` table (TOPIC-level, not per-person): topic, original_position, original_date, original_meeting, new_position, change_date, change_meeting, days_between. Built by `pipeline/src/normalize.py` `detect_direction_changes()` (~lines 428-461); supersedes chaining ~lines 305-326. Model `DirectionChange` in `pipeline/src/schema_types.py` (~lines 47-55). Warehouse DDL for `direction_changes` in `pipeline/src/warehouse.py` (~lines 84-92).

Implementation plan:
1. Pipeline (`normalize.py`): extend reversal detection to per-person. For each superseding decision chain on a topic, intersect `decided_by` of the original and the superseding decision; emit per-person reversal records: person, topic, original position + date + meeting, new position + date + meeting, days_between, confidence shift. Add a `PersonDirectionChange` model in `schema_types.py`.
2. Warehouse (`warehouse.py`): new `person_direction_changes` BigQuery table (mirror the `direction_changes` DDL + a `person` column). Load it in the warehouse step.
3. Agent (`chatbot/agent.py`): add `generate_deepthink_artifact(...)` returning `{"artifact_type": "deepthink", ...}` querying `person_direction_changes` (filter by person/topic/date as needed). Register it in the tools list (~lines 795-803).
4. Server (`chatbot/server.py`): add `"generate_deepthink_artifact"` to `ARTIFACT_TOOLS`; add a `DeepThinkArtifact` pydantic model to `_ARTIFACT_MODELS`; add a `"deepthink"` entry to `CANVAS_HINTS`. Restart backend after.
5. Frontend: `components/canvas/artifacts/DeepThinkArtifact.tsx` (who set the direction, what it was, when, the reversal, the time gap; mono labels, semantic colors); add `"deepthink"` to artifact-type unions in `lib/types.ts`, render it in `Canvas.tsx`, add a Canvas option in `components/chat/tools/ToolDrawer.tsx` (CANVAS_OPTIONS) and the `MessageBubble` artifact icon map.

Verification: re-run the relevant pipeline stages (normalize + warehouse) against existing extracted data and confirm `person_direction_changes` populates; ask DeepThink in chat; confirm the artifact renders; run `python pipeline/src/verify_rag.py` to confirm no retrieval regression.

IMPORTANT before running pipeline: re-running against the BigQuery warehouse (`strolid_meetings` dataset) is a data operation. Confirm the exact run steps with the user before executing. `pipeline/run_pipeline.py` orchestrates stages (extract -> extract_docs -> normalize -> warehouse -> embeddings -> verify); for Phase 4 only normalize + warehouse need to re-run (no re-embed required for the new table).

## Remaining roadmap after Phase 4

- Phase 5: per-person sentiment precomputed in the pipeline (new BigQuery table) + `get_sentiment_analysis` tool; wire the existing tool-drawer sentiment submenu (1v1 / 1-vs-all / all-by-individual) to real data.
- Phase 6: include `documents` (non-meeting docs) in `generate_timeline_artifact` and surface doc-derived starter prompts.
