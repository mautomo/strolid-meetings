import os
import sys
import json
import asyncio
from pathlib import Path
import docx
from pypdf import PdfReader
from google import genai
from google.genai import types
from pydantic import BaseModel

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema_types import ExtractedMeeting

MEETINGS_DIR = Path(__file__).resolve().parents[2] / "original-docs"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "extracted"

# Initialize Gen AI Client
# Pick up GEMINI_API_KEY from environment
client = genai.Client()
MODEL_ID = "gemini-2.5-flash"

EXCLUDE_FILES = {
    "9 FAQs_ Why Dealers Should Consider Strolid.docx",
    "Jake and Link Marketing Hooks.docx",
    "Marketing hooks 2 more about people.docx",
    "Marketing hooks 3.docx",
    "New marketing hooks.docx",
    "Sophia Outbound and Service inbound Plan.docx",
    "Strolid Website.docx",
    "Website Additions, subtractions and changes.docx",
    "README.md",
}

EXTRACTION_PROMPT = """You are a meeting intelligence analyst. Extract structured data from this meeting transcript/notes.

Return valid JSON matching the requested schema.

Rules:
- Extract ALL decisions, even small ones. A decision is any commitment, agreement, or direction set.
- For attendees, use full names. If only first names are used, include what's available.
- "confidence" should be "firm" if explicitly agreed, "tentative" if conditionally agreed, "exploratory" if just discussed.
- For action items, always try to identify an owner. If no owner is clear, use "Unassigned".
- Topics should be consistent kebab-case labels that could be reused across meetings (e.g., "website-refresh", "messaging-strategy", "buyer-targeting").
- Tensions include any pushback, disagreement, concern, or unresolved debate.
- referencesToPast includes any mention of prior meetings, earlier decisions, or "we discussed this before" type references.
- If the meeting notes include a transcript section, extract from BOTH the summary/details AND the transcript.
"""

def classify_meeting_type(filename: str) -> str:
    lower = filename.lower()
    if "leadership" in lower:
        return "leadership"
    if "marketing" in lower or "vconic" in lower:
        return "marketing"
    if "product" in lower or "roadmap" in lower:
        return "product"
    if any(k in lower for k in [
        "1-on-1", "1 on 1", "joe and michael", "michael _",
        "_ michael", "vin and michael", "call with michael", "michael and vin"
    ]):
        return "one-on-one"
    if "standup" in lower or "scrum" in lower:
        return "standup"
    if any(k in lower for k in ["planning", "prioritization", "alignment"]):
        return "strategy"
    return "other"

def extract_text_from_docx(file_path: Path) -> str:
    doc = docx.Document(file_path)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    full_text.append(para.text)
    return '\n'.join(full_text)

def extract_text_from_pdf(file_path: Path) -> str:
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text_parts.append(t)
    return "\n".join(text_parts)

async def extract_meeting_data(text: str, filename: str) -> ExtractedMeeting:
    meeting_type = classify_meeting_type(filename)
    prompt = f"{EXTRACTION_PROMPT}\n\nHint: This appears to be a '{meeting_type}' type meeting based on the filename: '{filename}'\n\nMeeting notes:\n\n{text}"

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedMeeting,
            temperature=0.1
        )
    )
    
    # The new SDK parses the JSON response into Pydantic model directly if response_schema is specified
    # However, sometimes we need to construct it from response.text
    try:
        data = ExtractedMeeting.model_validate_json(response.text)
        return data
    except Exception as e:
        print(f"Error parsing validation schema for {filename}: {e}")
        # Fallback to loading text as dict then validating
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        return ExtractedMeeting(**parsed)

async def process_file(filename: str, force: bool = False) -> bool:
    file_path = MEETINGS_DIR / filename
    output_id = Path(filename).stem
    output_path = OUTPUT_DIR / f"{output_id}.json"

    if output_path.exists() and not force:
        print(f"  Skipping (already extracted): {filename}")
        return True

    print(f"  Extracting: {filename}")
    try:
        if filename.endswith(".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif filename.endswith(".pdf"):
            text = extract_text_from_pdf(file_path)
        else:
            text = extract_text_from_docx(file_path)

        # Truncate very long transcripts to respect limits
        if len(text) > 50000:
            print(f"    Truncating {filename} from {len(text)} to 50000 chars")
            text = text[:50000] + "\n\n[TRUNCATED - remaining transcript omitted]"

        data = await extract_meeting_data(text, filename)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))
        return True
    except Exception as e:
        print(f"  FAILED to process {filename}: {e}")
        return False

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not MEETINGS_DIR.exists():
        print(f"Error: Original documents directory does not exist: {MEETINGS_DIR}")
        return

    all_files = os.listdir(MEETINGS_DIR)
    meeting_files = [
        f for f in all_files
        if (f.endswith(".docx") or f.endswith(".pdf") or f.endswith(".md"))
        and ("notes by gemini" in f.lower() or "leadership call" in f.lower())
        and f not in EXCLUDE_FILES
    ]

    # Deduplicate: if both DOCX/MD and PDF exist, only keep DOCX/MD
    groups = {}
    for f in meeting_files:
        stem = Path(f).stem
        groups.setdefault(stem, []).append(f)
        
    deduped_meetings = []
    for stem, files in groups.items():
        best_file = None
        for ext in [".docx", ".md", ".pdf"]:
            match = [f for f in files if f.lower().endswith(ext)]
            if match:
                best_file = match[0]
                break
        if best_file:
            deduped_meetings.append(best_file)
            
    meeting_files = deduped_meetings
    print(f"Found {len(meeting_files)} unique meeting files to process.\n")

    force = "--force" in sys.argv
    
    # Filter files that need to be processed
    to_process = []
    for f in meeting_files:
        output_path = OUTPUT_DIR / f"{Path(f).stem}.json"
        if not output_path.exists() or force:
            to_process.append(f)

    if not to_process:
        print("All files already extracted. Use --force to re-extract.")
        return

    print(f"Processing {len(to_process)} files...\n")

    # Process in batches to respect rate limits
    BATCH_SIZE = 3
    processed = 0
    failed = 0

    for i in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[i:i+BATCH_SIZE]
        tasks = [process_file(f, force=force) for f in batch]
        results = await asyncio.gather(*tasks)
        
        for success in results:
            if success:
                processed += 1
            else:
                failed += 1
        
        print(f"  Progress: {processed + failed}/{len(to_process)} ({failed} failed)\n")
        # Small delay between batches to respect rate limits
        await asyncio.sleep(1.0)

    print(f"\nExtraction complete: {processed} succeeded, {failed} failed.")
    print(f"Output directory: {OUTPUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
