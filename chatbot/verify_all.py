import asyncio
import sys
import io
from pathlib import Path
from google.genai import types

# Force UTF-8 for stdout and stderr on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure we can import from src/ and chatbot/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import build_agent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

async def test_chatbot():
    APP_NAME = "strolid_meeting_intelligence"
    SESSION_DB_URL = "sqlite+aiosqlite:///./adk_sessions.db"
    
    # 1. Initialize ADK 2.0 Runner
    print("Initializing ADK 2.0 Runner...")
    session_service = DatabaseSessionService(SESSION_DB_URL)
    runner = Runner(
        app_name=APP_NAME,
        agent=build_agent(),
        session_service=session_service,
    )
    
    user_id = "test_dev"
    session_id = "test_verify_session"
    
    # Verify/create session
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if session is None:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        
    # 2. Test RAG / SQL query metric
    prompt = "Compare Vinnie and Michael's decisions on marketing strategy and display their alignment score."
    print(f"\nUser: '{prompt}'")
    print("Assistant response stream:")
    print("-" * 50)
    
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if text:
                    sys.stdout.write(text)
                    sys.stdout.flush()
    print("\n" + "-" * 50)
    
    # 3. Test timeline artifact compilation
    prompt_timeline = "Create a timeline of all decisions made between October and December 2025."
    print(f"\nUser: '{prompt_timeline}'")
    print("Assistant response stream:")
    print("-" * 50)
    
    message_t = types.Content(role="user", parts=[types.Part(text=prompt_timeline)])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message_t
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if text:
                    sys.stdout.write(text)
                    sys.stdout.flush()
    print("\n" + "-" * 50)

if __name__ == "__main__":
    asyncio.run(test_chatbot())
