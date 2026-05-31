import os
import sys
import json
import time
import asyncio
from collections import deque, defaultdict
from pathlib import Path
from typing import AsyncGenerator, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud import bigquery

# Tools whose structured dict return value is an interactive canvas artifact.
ARTIFACT_TOOLS = {
    "generate_presentation_artifact",
    "generate_timeline_artifact",
    "generate_scorecard_artifact",
    "generate_comparison_artifact",
    "generate_deepthink_artifact",
}


def sse(event: dict) -> str:
    """Serialize an event dict as a Server-Sent Events frame."""
    return f"data: {json.dumps(event)}\n\n"


def extract_artifact(response) -> Optional[dict]:
    """Pull an artifact payload out of an ADK function-response.

    Tools return a dict (e.g. {"artifact_type": "scorecard", ...}). ADK may hand
    it back directly or wrapped under "result"/"output". Error returns
    ({"status": "error", ...}) carry no artifact_type and are ignored.
    """
    if not isinstance(response, dict):
        return None
    if "artifact_type" in response:
        return response
    for key in ("result", "output"):
        value = response.get(key)
        if isinstance(value, dict) and "artifact_type" in value:
            return value
    if len(response) == 1:
        value = next(iter(response.values()))
        if isinstance(value, dict) and "artifact_type" in value:
            return value
    return None


# --- Artifact schema validation (run before persisting to Firestore) ---
class _ArtifactBase(BaseModel):
    artifact_type: str
    title: str
    model_config = {"extra": "allow"}


class PresentationArtifact(_ArtifactBase):
    slides: list


class TimelineArtifact(_ArtifactBase):
    events: list


class ScorecardArtifact(_ArtifactBase):
    target: str
    reliability: float
    stats: dict


class ComparisonArtifact(_ArtifactBase):
    entity_a: str
    entity_b: str
    alignment_score: float


class DeepThinkArtifact(_ArtifactBase):
    reversals: list


_ARTIFACT_MODELS = {
    "presentation": PresentationArtifact,
    "timeline": TimelineArtifact,
    "scorecard": ScorecardArtifact,
    "comparison": ComparisonArtifact,
    "deepthink": DeepThinkArtifact,
}


def validate_artifact(payload: dict) -> bool:
    """Return True if the payload matches the schema for its artifact_type."""
    model = _ARTIFACT_MODELS.get(payload.get("artifact_type"))
    if model is None:
        return False
    try:
        model.model_validate(payload)
        return True
    except ValidationError as e:
        print(f"Artifact failed schema validation: {e}")
        return False


# Ensure we can import from src/ and chatbot/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import build_agent

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"
bq_client = bigquery.Client(project=PROJECT_ID)

# Initialize Firebase Admin
if not firebase_admin._apps:
    try:
        firebase_admin.initialize_app(options={'projectId': 'meeting-analysis-6c116'})
        print("Firebase Admin SDK initialized successfully for project meeting-analysis-6c116.")
    except Exception as e:
        print(f"Warning: Firebase Admin initialization failed: {e}. Running with mock Firestore.")

db = firestore.client() if firebase_admin._apps else None

# --- Access allowlist + roles (Firestore "members" collection, doc id = lowercased email) ---
# Bootstrap admins are always treated as admin even before the collection is seeded, so an
# operator can never lock themselves out. Enforcement is opt-in: until ALLOWLIST_ENFORCED is
# true, every authenticated user keeps full access (role defaults to "user"). This lets an
# admin build the allowlist first, then flip enforcement on.
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
ALLOWLIST_ENFORCED = os.getenv("ALLOWLIST_ENFORCED", "false").lower() in ("1", "true", "yes")
MEMBERS_COLLECTION = "members"
print(f"[access] ADMIN_EMAILS={ADMIN_EMAILS} ALLOWLIST_ENFORCED={ALLOWLIST_ENFORCED}")


def get_member(email: Optional[str]) -> Optional[dict]:
    """Return the member record for an email, or None if not allowlisted."""
    if not email or not db:
        return None
    try:
        snap = db.collection(MEMBERS_COLLECTION).document(email.lower()).get()
        return snap.to_dict() if snap.exists else None
    except Exception as e:
        print(f"Error reading member {email}: {e}")
        return None


def resolve_role(email: Optional[str]) -> Optional[str]:
    """Resolve a caller's role: bootstrap admins first, then the members collection, else None."""
    if email and email.lower() in ADMIN_EMAILS:
        return "admin"
    member = get_member(email)
    return member.get("role") if member else None


def _verify_token(authorization: Optional[str], x_firebase_auth: Optional[str]) -> dict:
    """Extract and verify the Firebase ID token, returning the decoded claims."""
    token = None
    if x_firebase_auth:
        token = x_firebase_auth
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization credentials")

    try:
        return auth.verify_id_token(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase ID Token: {e}")


async def get_current_user(
    authorization: str = Header(None),
    x_firebase_auth: str = Header(None)
) -> str:
    """Verify the Firebase ID token and return the UID, enforcing the allowlist when enabled."""
    decoded = _verify_token(authorization, x_firebase_auth)
    if ALLOWLIST_ENFORCED and resolve_role(decoded.get("email")) is None:
        raise HTTPException(status_code=403, detail="This account is not on the access allowlist.")
    return decoded["uid"]


async def get_current_principal(
    authorization: str = Header(None),
    x_firebase_auth: str = Header(None)
) -> dict:
    """Like get_current_user but returns identity + resolved role for /api/me and admin routes."""
    decoded = _verify_token(authorization, x_firebase_auth)
    email = decoded.get("email")
    role = resolve_role(email)
    if ALLOWLIST_ENFORCED and role is None:
        raise HTTPException(status_code=403, detail="This account is not on the access allowlist.")
    return {"uid": decoded["uid"], "email": email, "role": role or "user"}


async def require_admin(principal: dict = Depends(get_current_principal)) -> dict:
    """Allow only admins (bootstrap ADMIN_EMAILS or members with role 'admin')."""
    if principal["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return principal

app = FastAPI(title="Strolid Meeting Intelligence Chatbot API")

# Restrict CORS to the Firebase Hosting origins (and localhost for dev).
# Override with the ALLOWED_ORIGINS env var (comma-separated) if domains change.
DEFAULT_ORIGINS = (
    "https://meeting-analysis-6c116.web.app,"
    "https://meeting-analysis-6c116.firebaseapp.com,"
    "http://localhost:3000"
)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # Any localhost port is allowed in dev (Next picks 3001+ when 3000 is busy);
    # production requests still come from the explicit Firebase origins above.
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "x-firebase-auth"],
)

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    # Optional so the client can send explicit null when no filter is active.
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    selected_meeting_ids: Optional[list[str]] = None
    # Tool-drawer selections (Phase 2). topics filters retrieval; canvas_hint routes the
    # agent to a specific artifact generator; sentiment_mode is reserved for Phase 5 data.
    topics: Optional[list[str]] = None
    canvas_hint: Optional[str] = None
    sentiment_mode: Optional[str] = None


class MemberInvite(BaseModel):
    email: str
    role: str = "user"  # "admin" | "user"


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ShareRequest(BaseModel):
    email: str


# --- Basic per-user rate limiting (in-memory sliding window, per instance) ---
RATE_LIMIT_MAX = int(os.getenv("CHAT_RATE_LIMIT", "20"))   # requests per window
RATE_LIMIT_WINDOW = 60.0                                   # seconds
_rate_buckets: dict[str, deque] = defaultdict(deque)


def check_rate_limit(uid: str):
    # Best-effort, per-instance limiter. On Cloud Run with N instances the effective
    # limit is N * RATE_LIMIT_MAX and it resets on cold start; this is abuse damping,
    # not strict quota enforcement.
    now = time.monotonic()
    bucket = _rate_buckets[uid]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down and try again shortly.")
    bucket.append(now)

    # Opportunistic sweep so departed users do not leak empty deques over time.
    if len(_rate_buckets) > 5000:
        for stale in [k for k, v in _rate_buckets.items() if not v]:
            del _rate_buckets[stale]

APP_NAME = "strolid_meeting_intelligence"
SESSION_DB_URL = "sqlite+aiosqlite:///./adk_sessions.db"

async def get_meeting_context(meeting_id: str) -> str:
    """Query relational BigQuery tables to construct a rich metadata context block for the meeting.

    The four lookups run concurrently (threads, since the BigQuery client is sync) with an
    overall timeout so a slow query can't silently stall the chat stream.
    """
    sql_meeting = f"""
    SELECT title, date, type, summary, sentiment_score, tension_score
    FROM `{PROJECT_ID}.{DATASET_ID}.meetings`
    WHERE meeting_id = @meeting_id LIMIT 1
    """
    sql_attendees = f"""
    SELECT person_name
    FROM `{PROJECT_ID}.{DATASET_ID}.meeting_attendees`
    WHERE meeting_id = @meeting_id
    """
    sql_decisions = f"""
    SELECT description, confidence, topic, ARRAY_TO_STRING(decided_by, ', ') as decided_by
    FROM `{PROJECT_ID}.{DATASET_ID}.decisions`
    WHERE meeting_id = @meeting_id
    """
    sql_actions = f"""
    SELECT task, owner, status
    FROM `{PROJECT_ID}.{DATASET_ID}.action_items`
    WHERE meeting_id = @meeting_id
    """

    def run(sql: str):
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("meeting_id", "STRING", meeting_id)]
        )
        return list(bq_client.query(sql, job_config=job_config).result())

    try:
        res_meeting, res_attendees, res_decisions, res_actions = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(run, sql_meeting),
                asyncio.to_thread(run, sql_attendees),
                asyncio.to_thread(run, sql_decisions),
                asyncio.to_thread(run, sql_actions),
            ),
            timeout=20,
        )
        if not res_meeting:
            return ""

        row = res_meeting[0]
        title = row["title"]
        date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
        m_type = row["type"]
        summary = row["summary"]
        sentiment = row["sentiment_score"] or 0.0
        tension = row["tension_score"] or 0.0
        attendees = [r["person_name"] for r in res_attendees]

        # Format markdown context
        ctx = [
            f"[System Context: The user has selected the active meeting '{title}' (Held: {date_str}, Type: {m_type}).",
            "Here is the verified relational metadata for this meeting from the database:",
            f"- **Summary**: {summary}",
            f"- **Sentiment Score**: {sentiment:.2f} | **Tension Score**: {tension:.2f}",
            f"- **Attendees**: {', '.join(attendees) if attendees else 'None specified'}"
        ]

        if res_decisions:
            ctx.append("- **Decisions Logged**:")
            for d in res_decisions:
                decided_by_str = f" by {d['decided_by']}" if d['decided_by'] else ""
                ctx.append(f"  - [{d['confidence'].upper()}] \"{d['description']}\"{decided_by_str} (Topic: {d['topic']})")
        else:
            ctx.append("- **Decisions Logged**: None")

        if res_actions:
            ctx.append("- **Action Items Assigned**:")
            for a in res_actions:
                ctx.append(f"  - [{a['status'].upper()}] to {a['owner']}: \"{a['task']}\"")
        else:
            ctx.append("- **Action Items Assigned**: None")

        ctx.append("Keep this context in mind when answering. If the user asks general or structural questions about this meeting (e.g. who attended, what was decided, what action items were assigned), rely on this verified metadata directly. For detailed transcript-level details not present in this summary, use the `rag_search` tool.]\n\n")

        return "\n".join(ctx)
    except Exception as e:
        print(f"Error fetching meeting context details: {e}")
        return f"[System Context: Meeting ID: {meeting_id}. Keep this in mind when answering.]\n\n"

# Initialize ADK Runner
session_service = DatabaseSessionService(SESSION_DB_URL)
adk_runner = Runner(
    app_name=APP_NAME,
    agent=build_agent(),
    session_service=session_service,
)


def _persist_messages(session_id: str, user_message: str, assistant_content: str, artifact_payload: Optional[dict]):
    """Best-effort Firestore persistence under conversations/{id}. Never raises into the
    request path. The conversation doc is created/owned by ensure_conversation_owner."""
    if not db:
        return
    try:
        conv = db.collection(CONVERSATIONS_COLLECTION).document(session_id)
        msgs = conv.collection("messages")
        msgs.add({
            "role": "user",
            "content": user_message,
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
        msg_doc = {
            "role": "assistant",
            "content": assistant_content,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
        if artifact_payload and validate_artifact(artifact_payload):
            msg_doc["artifact"] = artifact_payload
            conv.collection("artifacts").add({
                "type": artifact_payload.get("artifact_type"),
                "title": artifact_payload.get("title", "Untitled"),
                "payload": artifact_payload,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })
        msgs.add(msg_doc)
        conv.update({"updatedAt": firestore.SERVER_TIMESTAMP})
    except Exception as e:
        print(f"Error logging conversation to Firestore: {e}")


# Maps a tool-drawer canvas selection to the generator the agent should call.
CANVAS_HINTS = {
    "timeline": "generate_timeline_artifact",
    "presentation": "generate_presentation_artifact",
    "scorecard": "generate_scorecard_artifact",
    "comparison": "generate_comparison_artifact",
    "deepthink": "generate_deepthink_artifact",
}


async def stream_response(
    session_id: str,
    user_id: str,
    user_message: str,
    start_date: str = None,
    end_date: str = None,
    selected_meeting_ids: list[str] = None,
    topics: list[str] = None,
    canvas_hint: str = None,
    sentiment_mode: str = None,
) -> AsyncGenerator[str, None]:
    """Stream the agent's response as Server-Sent Events.

    Emits typed frames: {"type": "token"|"artifact"|"error"|"done", ...}. Text comes
    directly from ADK's streamed events (event.partial / is_final_response); artifacts
    come from tool function-responses. No JSON is scraped out of model text.
    """
    accumulated_text = ""
    artifact_payload = None
    completed = False

    try:
        # Verify/create ADK session
        session = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is None:
            await session_service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )

        # Context injection when the scope is a single meeting (decoupled from the
        # conversation id, which is now a private owned-conversation key).
        context_prefix = ""
        if selected_meeting_ids and len(selected_meeting_ids) == 1:
            context_prefix = await get_meeting_context(selected_meeting_ids[0])

        filter_contexts = []
        if start_date:
            filter_contexts.append(f"Start Date: {start_date}")
        if end_date:
            filter_contexts.append(f"End Date: {end_date}")
        if selected_meeting_ids:
            filter_contexts.append(f"Selected Meeting IDs: {selected_meeting_ids}")
        if topics:
            filter_contexts.append(f"Topics: {topics}")

        if filter_contexts:
            context_prefix += f"[System Context - Active Filters: {'; '.join(filter_contexts)}. Call tools using these filters. If no meeting ID list is specified in a tool invocation, use these selected meeting IDs and date range as default arguments. Pass the topics above as the topics filter where the tool supports it. Do not mention this system context in your plain text reply unless asked.]\n\n"

        canvas_tool = CANVAS_HINTS.get((canvas_hint or "").lower())
        if canvas_tool:
            context_prefix += f"[System Context - The user opened the {canvas_hint} canvas. Produce that artifact by calling the {canvas_tool} tool with the active filters above.]\n\n"

        agent_message_text = context_prefix + user_message
        message = types.Content(role="user", parts=[types.Part(text=agent_message_text)])

        async for event in adk_runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            # Artifacts arrive as structured tool function-responses. Validate before
            # emitting so the stream and the persisted record stay consistent.
            for f_resp in event.get_function_responses():
                if f_resp.name in ARTIFACT_TOOLS:
                    payload = extract_artifact(f_resp.response)
                    if payload and validate_artifact(payload):
                        artifact_payload = payload
                        yield sse({"type": "artifact", "payload": payload})
                    elif payload:
                        print(f"Dropping malformed artifact from {f_resp.name}: {payload.get('artifact_type')}")

            # Text: stream partial deltas. The final event carries the complete
            # aggregated text, so emit only the suffix not already streamed. This
            # avoids both duplicating the streamed text and dropping a final tail,
            # regardless of whether the model streams token-by-token.
            if event.content and event.content.parts:
                text = "".join(
                    p.text for p in event.content.parts if getattr(p, "text", None)
                )
                if text:
                    if getattr(event, "partial", False):
                        accumulated_text += text
                        yield sse({"type": "token", "text": text})
                    elif event.is_final_response():
                        if text.startswith(accumulated_text):
                            remainder = text[len(accumulated_text):]
                            accumulated_text = text
                        else:
                            # Final text diverges from the streamed deltas (rare);
                            # treat it as additional content rather than dropping it.
                            remainder = text
                            accumulated_text += text
                        if remainder:
                            yield sse({"type": "token", "text": remainder})

        completed = True
        yield sse({"type": "done"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error during agent run: {e}")
        yield sse({
            "type": "error",
            "message": "The assistant hit an error generating a response. Please try again.",
        })
        return
    finally:
        # Persist only on a clean completion. On error or client disconnect
        # (GeneratorExit), skip so we never store a partial or fabricated turn.
        if completed:
            content = accumulated_text.strip()
            if not content and artifact_payload:
                content = "Here is the generated canvas."
            if content or artifact_payload:
                _persist_messages(session_id, user_message, content, artifact_payload)

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, principal: dict = Depends(get_current_principal)):
    """Streams the chat response as Server-Sent Events (SSE). session_id is the conversation id."""
    check_rate_limit(principal["uid"])
    # Enforce ownership: create on first send, or reject if the conversation belongs to
    # someone else (read-only sharees cannot post).
    ensure_conversation_owner(request.session_id, principal, request)
    request.user_id = principal["uid"]
    return StreamingResponse(
        stream_response(
            request.session_id,
            request.user_id,
            request.message,
            start_date=request.start_date,
            end_date=request.end_date,
            selected_meeting_ids=request.selected_meeting_ids,
            topics=request.topics,
            canvas_hint=request.canvas_hint,
            sentiment_mode=request.sentiment_mode,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/api/meetings")
def get_meetings(uid: str = Depends(get_current_user)):
    """Returns a list of all meetings sorted by date descending"""
    try:
        sql = f"SELECT meeting_id, title, date FROM `{PROJECT_ID}.{DATASET_ID}.meetings` ORDER BY date DESC"
        query_job = bq_client.query(sql)
        results = list(query_job.result())
        meetings_list = []
        for row in results:
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
            meetings_list.append({
                "meeting_id": row["meeting_id"],
                "title": row["title"],
                "date": date_str
            })
        return {"meetings": meetings_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch meetings: {e}")

@app.get("/api/topics")
def get_topics(uid: str = Depends(get_current_user)):
    """Returns meeting topics for the tool-drawer topics picker, most-discussed first."""
    try:
        sql = f"""
        SELECT label, mention_count
        FROM `{PROJECT_ID}.{DATASET_ID}.topics`
        ORDER BY mention_count DESC
        """
        results = list(bq_client.query(sql).result())
        topics_list = [
            {"label": row["label"], "mention_count": row["mention_count"]}
            for row in results
        ]
        return {"topics": topics_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch topics: {e}")

@app.get("/api/me")
def get_me(principal: dict = Depends(get_current_principal)):
    """Identity + resolved role for the signed-in user, plus whether the allowlist is enforced."""
    return {
        "email": principal["email"],
        "role": principal["role"],
        "allowlist_enforced": ALLOWLIST_ENFORCED,
    }


def _serialize_member(email: str, data: dict) -> dict:
    created = data.get("createdAt")
    return {
        "email": email,
        "role": data.get("role", "user"),
        "status": data.get("status", "invited"),
        "invitedBy": data.get("invitedBy"),
        "createdAt": created.isoformat() if hasattr(created, "isoformat") else None,
    }


@app.get("/api/admin/members")
def list_members(_admin: dict = Depends(require_admin)):
    """List allowlisted members (admin only)."""
    if not db:
        raise HTTPException(status_code=503, detail="Member store unavailable.")
    docs = db.collection(MEMBERS_COLLECTION).stream()
    members = [_serialize_member(d.id, d.to_dict() or {}) for d in docs]
    members.sort(key=lambda m: m["email"])
    return {"members": members}


@app.post("/api/admin/members")
def upsert_member(invite: MemberInvite, admin: dict = Depends(require_admin)):
    """Add or update an allowlisted member (admin only). Invitee gains access on next sign-in."""
    if not db:
        raise HTTPException(status_code=503, detail="Member store unavailable.")
    email = invite.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    if invite.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'.")
    doc_ref = db.collection(MEMBERS_COLLECTION).document(email)
    existing = doc_ref.get()
    payload = {
        "role": invite.role,
        "status": existing.to_dict().get("status", "invited") if existing.exists else "invited",
        "invitedBy": admin["email"],
    }
    if not existing.exists:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP
    doc_ref.set(payload, merge=True)
    return {"status": "success", "email": email, "role": invite.role}


@app.delete("/api/admin/members/{email}")
def remove_member(email: str, admin: dict = Depends(require_admin)):
    """Remove an allowlisted member (admin only)."""
    if not db:
        raise HTTPException(status_code=503, detail="Member store unavailable.")
    target = email.strip().lower()
    if target in ADMIN_EMAILS:
        raise HTTPException(status_code=400, detail="Bootstrap admins cannot be removed from the panel.")
    db.collection(MEMBERS_COLLECTION).document(target).delete()
    return {"status": "success", "email": target}


# --- Conversations (owned by creator, optionally shared read-only by email) ---
CONVERSATIONS_COLLECTION = "conversations"


def _scope_from_request(req: "ChatRequest") -> dict:
    return {
        "startDate": req.start_date,
        "endDate": req.end_date,
        "meetingIds": req.selected_meeting_ids or [],
        "topics": req.topics or [],
    }


def ensure_conversation_owner(conversation_id: str, principal: dict, req: "ChatRequest"):
    """Create the conversation on first send, or verify the caller owns it. Read-only
    sharees (owner != caller) are rejected. Also persists the latest scope and derives a
    title from the first user message."""
    if not db:
        return
    ref = db.collection(CONVERSATIONS_COLLECTION).document(conversation_id)
    snap = ref.get()
    scope = _scope_from_request(req)
    title = (req.message or "").strip()[:60] or "New conversation"
    if not snap.exists:
        ref.set({
            "ownerUid": principal["uid"],
            "ownerEmail": principal["email"],
            "title": title,
            "sharedWith": [],
            "scope": scope,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        })
        return
    data = snap.to_dict() or {}
    if data.get("ownerUid") != principal["uid"]:
        raise HTTPException(status_code=403, detail="You can only post to conversations you own.")
    updates = {"scope": scope, "updatedAt": firestore.SERVER_TIMESTAMP}
    if data.get("title") in (None, "", "New conversation"):
        updates["title"] = title
    ref.update(updates)


def _serialize_conversation(doc, uid: str) -> dict:
    data = doc.to_dict() or {}
    updated = data.get("updatedAt")
    return {
        "id": doc.id,
        "title": data.get("title", "New conversation"),
        "ownerEmail": data.get("ownerEmail"),
        "sharedWith": data.get("sharedWith", []),
        "scope": data.get("scope", {}),
        "isOwner": data.get("ownerUid") == uid,
        "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else None,
    }


@app.post("/api/conversations")
def create_conversation(body: ConversationCreate, principal: dict = Depends(get_current_principal)):
    """Create an empty private conversation owned by the caller."""
    if not db:
        raise HTTPException(status_code=503, detail="Conversation store unavailable.")
    ref = db.collection(CONVERSATIONS_COLLECTION).document()
    ref.set({
        "ownerUid": principal["uid"],
        "ownerEmail": principal["email"],
        "title": (body.title or "New conversation").strip()[:60] or "New conversation",
        "sharedWith": [],
        "scope": {},
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })
    return {"id": ref.id}


@app.get("/api/conversations")
def list_conversations(principal: dict = Depends(get_current_principal)):
    """List conversations the caller owns or has been shared on, newest first."""
    if not db:
        raise HTTPException(status_code=503, detail="Conversation store unavailable.")
    coll = db.collection(CONVERSATIONS_COLLECTION)
    seen, items = set(), []
    for doc in coll.where("ownerUid", "==", principal["uid"]).stream():
        seen.add(doc.id)
        items.append(_serialize_conversation(doc, principal["uid"]))
    if principal["email"]:
        for doc in coll.where("sharedWith", "array_contains", principal["email"]).stream():
            if doc.id not in seen:
                items.append(_serialize_conversation(doc, principal["uid"]))
    items.sort(key=lambda c: c["updatedAt"] or "", reverse=True)
    return {"conversations": items}


def _owned_conversation_ref(conversation_id: str, principal: dict):
    if not db:
        raise HTTPException(status_code=503, detail="Conversation store unavailable.")
    ref = db.collection(CONVERSATIONS_COLLECTION).document(conversation_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if (snap.to_dict() or {}).get("ownerUid") != principal["uid"]:
        raise HTTPException(status_code=403, detail="Only the owner can manage this conversation.")
    return ref


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, principal: dict = Depends(get_current_principal)):
    """Delete a conversation the caller owns (messages become unreadable via rules)."""
    ref = _owned_conversation_ref(conversation_id, principal)
    ref.delete()
    return {"status": "success", "id": conversation_id}


@app.post("/api/conversations/{conversation_id}/share")
def share_conversation(conversation_id: str, body: ShareRequest, principal: dict = Depends(get_current_principal)):
    """Share a conversation read-only with another user by email (owner only)."""
    ref = _owned_conversation_ref(conversation_id, principal)
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    ref.update({"sharedWith": firestore.ArrayUnion([email]), "updatedAt": firestore.SERVER_TIMESTAMP})
    return {"status": "success", "email": email}


@app.delete("/api/conversations/{conversation_id}/share/{email}")
def unshare_conversation(conversation_id: str, email: str, principal: dict = Depends(get_current_principal)):
    """Revoke a user's read access to a conversation (owner only)."""
    ref = _owned_conversation_ref(conversation_id, principal)
    ref.update({"sharedWith": firestore.ArrayRemove([email.strip().lower()]), "updatedAt": firestore.SERVER_TIMESTAMP})
    return {"status": "success", "email": email.strip().lower()}


@app.get("/api/stats")
def get_stats(uid: str = Depends(get_current_user)):
    """Returns summary analytics counts from the warehouse"""
    try:
        sql_meetings = f"SELECT COUNT(*) as count FROM `{PROJECT_ID}.{DATASET_ID}.meetings`"
        sql_decisions = f"SELECT COUNT(*) as count FROM `{PROJECT_ID}.{DATASET_ID}.decisions`"

        meetings_count = list(bq_client.query(sql_meetings).result())[0]["count"]
        decisions_count = list(bq_client.query(sql_decisions).result())[0]["count"]

        return {
            "meetings_count": meetings_count,
            "decisions_count": decisions_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")

@app.get("/api/test_db")
def test_db(uid: str = Depends(get_current_user)):
    global db
    if db is None:
        return {"status": "error", "message": "db is None"}
    try:
        doc_ref = db.collection("sessions").document("test_api")
        doc_ref.set({"status": "healthy"})
        return {"status": "success", "data": doc_ref.get().to_dict()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
