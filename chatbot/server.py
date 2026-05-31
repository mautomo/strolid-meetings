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


_ARTIFACT_MODELS = {
    "presentation": PresentationArtifact,
    "timeline": TimelineArtifact,
    "scorecard": ScorecardArtifact,
    "comparison": ComparisonArtifact,
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

async def get_current_user(
    authorization: str = Header(None),
    x_firebase_auth: str = Header(None)
) -> str:
    """Verifies the Firebase ID token from the x-firebase-auth or Authorization header and returns the UID."""
    token = None
    if x_firebase_auth:
        token = x_firebase_auth
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization credentials")

    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase ID Token: {e}")

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
    allow_methods=["GET", "POST", "OPTIONS"],
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
    """Best-effort Firestore persistence. Never raises into the request path."""
    if not db:
        return
    try:
        msgs = db.collection("sessions").document(session_id).collection("messages")
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
            db.collection("sessions").document(session_id).collection("artifacts").add({
                "type": artifact_payload.get("artifact_type"),
                "title": artifact_payload.get("title", "Untitled"),
                "payload": artifact_payload,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })
        msgs.add(msg_doc)
    except Exception as e:
        print(f"Error logging conversation to Firestore: {e}")


async def stream_response(
    session_id: str,
    user_id: str,
    user_message: str,
    start_date: str = None,
    end_date: str = None,
    selected_meeting_ids: list[str] = None
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

        # Context injection for meeting-specific sessions
        context_prefix = ""
        if session_id.startswith("session-meeting-"):
            meeting_id = session_id.replace("session-meeting-", "")
            context_prefix = await get_meeting_context(meeting_id)

        filter_contexts = []
        if start_date:
            filter_contexts.append(f"Start Date: {start_date}")
        if end_date:
            filter_contexts.append(f"End Date: {end_date}")
        if selected_meeting_ids:
            filter_contexts.append(f"Selected Meeting IDs: {selected_meeting_ids}")

        if filter_contexts:
            context_prefix += f"[System Context - Active Filters: {'; '.join(filter_contexts)}. Call tools using these filters. If no meeting ID list is specified in a tool invocation, use these selected meeting IDs and date range as default arguments. Do not mention this system context in your plain text reply unless asked.]\n\n"

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
async def chat_endpoint(request: ChatRequest, uid: str = Depends(get_current_user)):
    """Streams the chat response as Server-Sent Events (SSE)."""
    check_rate_limit(uid)
    request.user_id = uid
    return StreamingResponse(
        stream_response(
            request.session_id,
            request.user_id,
            request.message,
            start_date=request.start_date,
            end_date=request.end_date,
            selected_meeting_ids=request.selected_meeting_ids
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
