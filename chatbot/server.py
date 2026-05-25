import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud import bigquery

class StreamFilter:
    def __init__(self):
        self.buffer = ""
        self.in_block = False
        self.block_start_marker = "```json"
        self.block_end_marker = "```"
        self.is_fence = False

    def feed(self, chunk: str) -> str:
        self.buffer += chunk
        output = ""
        
        while True:
            if not self.in_block:
                start_idx_fence = self.buffer.find("```json")
                start_idx_brace = self.buffer.find("{")
                
                # Determine which comes first
                start_idx = -1
                is_fence = False
                if start_idx_fence != -1 and start_idx_brace != -1:
                    if start_idx_fence < start_idx_brace:
                        start_idx = start_idx_fence
                        is_fence = True
                    else:
                        start_idx = start_idx_brace
                elif start_idx_fence != -1:
                    start_idx = start_idx_fence
                    is_fence = True
                elif start_idx_brace != -1:
                    start_idx = start_idx_brace
                
                if start_idx != -1:
                    output += self.buffer[:start_idx]
                    self.buffer = self.buffer[start_idx:]
                    self.in_block = True
                    self.is_fence = is_fence
                else:
                    keep_len = 7
                    if len(self.buffer) > keep_len:
                        output += self.buffer[:-keep_len]
                        self.buffer = self.buffer[-keep_len:]
                    break
            else:
                if self.is_fence:
                    end_idx = self.buffer.find("```", 7)
                    if end_idx != -1:
                        block_content = self.buffer[:end_idx + 3]
                        self.buffer = self.buffer[end_idx + 3:]
                        self.in_block = False
                        
                        if "artifact_type" not in block_content:
                            output += block_content
                    else:
                        break
                else:
                    brace_count = 0
                    match_idx = -1
                    for idx, char in enumerate(self.buffer):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                match_idx = idx
                                break
                    if match_idx != -1:
                        block_content = self.buffer[:match_idx + 1]
                        self.buffer = self.buffer[match_idx + 1:]
                        self.in_block = False
                        
                        if "artifact_type" not in block_content:
                            output += block_content
                    else:
                        break
        return output

    def flush(self) -> str:
        if self.in_block:
            if "artifact_type" in self.buffer:
                return ""
        return self.buffer

def clean_assistant_content(text: str) -> str:
    pattern_fence = r'```json\s*\{.*?\"artifact_type\".*?\}\s*```'
    cleaned = re.sub(pattern_fence, '', text, flags=re.DOTALL)
    
    pattern_bare = r'\{\s*\"artifact_type\".*?\}'
    cleaned = re.sub(pattern_bare, '', cleaned, flags=re.DOTALL)
    
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = "Here is the generated presentation canvas:"
    return cleaned


# Ensure we can import from src/ and chatbot/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import build_agent

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"
bq_client = bigquery.Client(project=PROJECT_ID)

# Initialize Firebase Admin
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str

APP_NAME = "strolid_meeting_intelligence"
SESSION_DB_URL = "sqlite+aiosqlite:///./adk_sessions.db"

# Initialize ADK Runner
session_service = DatabaseSessionService(SESSION_DB_URL)
adk_runner = Runner(
    app_name=APP_NAME,
    agent=build_agent(),
    session_service=session_service,
)

async def stream_response(session_id: str, user_id: str, user_message: str) -> AsyncGenerator[str, None]:
    # 1. Write user message to Firestore
    if db:
        try:
            db.collection("sessions").document(session_id).collection("messages").add({
                "role": "user",
                "content": user_message,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            print(f"Error logging user message to Firestore: {e}")
            
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
        try:
            sql = f"SELECT title, date FROM `{PROJECT_ID}.{DATASET_ID}.meetings` WHERE meeting_id = @meeting_id LIMIT 1"
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("meeting_id", "STRING", meeting_id)]
            )
            res = list(bq_client.query(sql, job_config=job_config).result())
            if res:
                title = res[0]["title"]
                date = res[0]["date"].strftime("%Y-%m-%d") if hasattr(res[0]["date"], "strftime") else str(res[0]["date"])
                context_prefix = f"[System Context: The user has currently selected the meeting '{title}' held on {date} (ID: {meeting_id}) in the UI. Keep this in mind when answering questions about 'this meeting' or 'the meeting' without explicit names. You can query its details using your tools.]\n\n"
        except Exception as e:
            print(f"Error fetching meeting context: {e}")

    # 2. Run ADK Agent and stream tokens
    agent_message_text = context_prefix + user_message
    message = types.Content(role="user", parts=[types.Part(text=agent_message_text)])
    
    accumulated_text = ""
    artifact_payload = None
    stream_filter = StreamFilter()
    
    async for event in adk_runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if text:
                    accumulated_text += text
                    filtered = stream_filter.feed(text)
                    if filtered:
                        yield filtered
                        
    flushed = stream_filter.flush()
    if flushed:
        yield flushed
                    
    # 3. Post-process accumulated text to extract any artifact payloads
    # Artifacts are output by tools as valid JSON strings
    try:
        # Check if the response contains any JSON block matching timeline or presentation schemas
        cleaned_text = accumulated_text.strip()
        if "artifact_type" in cleaned_text:
            # Try to parse the entire text if it's pure JSON, or search for markdown blocks
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                # Find start and end of JSON block
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip().startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json:
                        json_lines.append(line)
                json_str = "\n".join(json_lines)
            else:
                json_str = cleaned_text
                
            parsed = json.loads(json_str)
            if isinstance(parsed, dict) and "artifact_type" in parsed:
                artifact_payload = parsed
                print(f"Extracted artifact payload of type: {parsed.get('artifact_type')}")
    except Exception as e:
        # Not an artifact or failed parsing, which is normal for regular chat responses
        pass
        
    # 4. Write assistant response and artifact metadata to Firestore
    if db:
        try:
            cleaned_content = clean_assistant_content(accumulated_text)
            msg_doc = {
                "role": "assistant",
                "content": cleaned_content,
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            if artifact_payload:
                msg_doc["artifact"] = artifact_payload
                # Also save to dedicated artifacts subcollection for direct references
                db.collection("sessions").document(session_id).collection("artifacts").add({
                    "type": artifact_payload.get("artifact_type"),
                    "title": artifact_payload.get("title", "Untitled"),
                    "payload": artifact_payload,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
            
            db.collection("sessions").document(session_id).collection("messages").add(msg_doc)
        except Exception as e:
            print(f"Error logging assistant response to Firestore: {e}")

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, uid: str = Depends(get_current_user)):
    """Exposes chat streaming via SSE (Server-Sent Events)"""
    request.user_id = uid
    return StreamingResponse(
        stream_response(request.session_id, request.user_id, request.message),
        media_type="text/plain"
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
