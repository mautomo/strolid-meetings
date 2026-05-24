import asyncio
import sys
import io
from pathlib import Path

# Force UTF-8 for stdout and stderr on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract_text_from_docx, extract_meeting_data

async def main():
    file_name = "1-on-1 Joe and Michael - 2025_07_01 10_55 EDT - Notes by Gemini.docx"
    doc_path = Path(__file__).resolve().parents[2] / "original-docs" / file_name
    
    if not doc_path.exists():
        print(f"Error: Test file not found at {doc_path}")
        return
        
    print(f"Reading file: {file_name}")
    text = extract_text_from_docx(doc_path)
    print(f"Extracted {len(text)} characters of text. First 300 chars:")
    print("-" * 40)
    print(text[:300])
    print("-" * 40)
    
    print("\nRunning Gemini structured extraction (gemini-2.5-flash)...")
    try:
        meeting_data = await extract_meeting_data(text[:10000], file_name)
        print("Success! Parsed meeting details:")
        print(f"  Title: {meeting_data.title}")
        print(f"  Date: {meeting_data.date}")
        print(f"  Attendees: {', '.join(meeting_data.attendees)}")
        print(f"  Decisions Extracted: {len(meeting_data.decisions)}")
        for d in meeting_data.decisions:
            print(f"    - [{d.confidence}] {d.description} (Topic: {d.topic})")
        print(f"  Action Items Extracted: {len(meeting_data.actionItems)}")
        for a in meeting_data.actionItems:
            owner = a.owner
            print(f"    - {a.task} (Owner: {owner})")
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
