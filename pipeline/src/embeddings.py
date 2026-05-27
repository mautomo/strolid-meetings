import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from google import genai
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract_text_from_docx, extract_text_from_pdf
from schema_types import ExtractedMeeting

MEETINGS_DIR = Path(__file__).resolve().parents[2] / "original-docs"
EXTRACTED_DIR = Path(__file__).resolve().parents[1] / "data" / "extracted"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"
TABLE_ID = "embeddings"

# Initialize Clients
genai_client = genai.Client()
bq_client = bigquery.Client(project=PROJECT_ID)

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

def create_embeddings_table_if_not_exists():
    table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), TABLE_ID)
    schema = [
        bigquery.SchemaField("chunk_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date", "DATE"),
        bigquery.SchemaField("text", "STRING"),
        bigquery.SchemaField("attendees", "STRING", mode="REPEATED"),
        bigquery.SchemaField("topics", "STRING", mode="REPEATED"),
        bigquery.SchemaField("sentiment", "STRING"),
        bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED")
    ]
    try:
        bq_client.get_table(table_ref)
        print(f"Table '{TABLE_ID}' already exists.")
    except NotFound:
        table = bigquery.Table(table_ref, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="date"
        )
        bq_client.create_table(table)
        print(f"Table '{TABLE_ID}' created successfully.")

def chunk_dialogue(text: str, min_chars: int = 800, max_chars: int = 1500) -> list[str]:
    # Clean text and split by double-newline
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    chunks = []
    current_chunk = []
    current_len = 0
    
    for block in blocks:
        block_len = len(block)
        if block_len > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            # Split the large block into smaller pieces by single newline
            sub_blocks = [sb.strip() for sb in block.split("\n") if sb.strip()]
            for sb in sub_blocks:
                sb_len = len(sb)
                if sb_len > max_chars:
                    # character split
                    start = 0
                    while start < sb_len:
                        chunks.append(sb[start:start+max_chars])
                        start += max_chars
                else:
                    if current_len + sb_len + 2 > max_chars:
                        if current_chunk:
                            chunks.append("\n\n".join(current_chunk))
                        current_chunk = [sb]
                        current_len = sb_len
                    else:
                        current_chunk.append(sb)
                        current_len += sb_len + (2 if current_len > 0 else 0)
            continue
            
        if current_len + block_len + 2 > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            current_len = block_len
        else:
            current_chunk.append(block)
            current_len += block_len + (2 if current_len > 0 else 0)
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks

def chunk_paragraphs(text: str, min_chars: int = 800, max_chars: int = 1500) -> list[str]:
    # Clean text and split by double-newline first, if that results in too few blocks, try single newline
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if len(blocks) <= 1:
        blocks = [b.strip() for b in text.split("\n") if b.strip()]
        
    chunks = []
    current_chunk = []
    current_len = 0
    
    for block in blocks:
        block_len = len(block)
        if block_len > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            # Split large block by sentence
            sentences = re.split(r'(?<=[.!?])\s+', block)
            for sentence in sentences:
                s_len = len(sentence)
                if s_len > max_chars:
                    # character split
                    start = 0
                    while start < s_len:
                        chunks.append(sentence[start:start+max_chars])
                        start += max_chars
                else:
                    if current_len + s_len + 1 > max_chars:
                        if current_chunk:
                            chunks.append(" ".join(current_chunk))
                        current_chunk = [sentence]
                        current_len = s_len
                    else:
                        current_chunk.append(sentence)
                        current_len += s_len + (1 if current_len > 0 else 0)
            continue
            
        if current_len + block_len + 2 > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            current_len = block_len
        else:
            current_chunk.append(block)
            current_len += block_len + (2 if current_len > 0 else 0)
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks

def chunk_text(text: str, is_transcript: bool = True, min_chars: int = 800, max_chars: int = 1500) -> list[str]:
    if is_transcript:
        return chunk_dialogue(text, min_chars, max_chars)
    else:
        return chunk_paragraphs(text, min_chars, max_chars)

def generate_embedding(text: str) -> list[float]:
    response = genai_client.models.embed_content(
        model="gemini-embedding-2",
        contents=text
    )
    return response.embeddings[0].values

def truncate_embeddings_table():
    table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), TABLE_ID)
    try:
        bq_client.get_table(table_ref)
        sql = f"TRUNCATE TABLE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`"
        print(f"Truncating BigQuery embeddings table...")
        bq_client.query(sql).result()
        print("  Successfully truncated embeddings table.")
    except NotFound:
        print("Embeddings table does not exist yet. It will be created.")
        create_embeddings_table_if_not_exists()

def process_and_embed_all():
    truncate_embeddings_table()
    
    # --- Part 1: Process Meeting Transcripts ---
    all_files = os.listdir(MEETINGS_DIR)
    meeting_files = [
        f for f in all_files
        if (f.endswith(".docx") or f.endswith(".pdf") or (f.endswith(".md") and "Notes by Gemini" in f))
        and f not in EXCLUDE_FILES
    ]
    
    # Deduplicate meetings: if both docx/md and pdf exist, keep docx/md
    groups = {}
    for f in meeting_files:
        stem = Path(f).stem
        # Clean any trailing copy numbers like " (1)" or " (2)"
        stem = re.sub(r'\s*\(\d+\)$', '', stem).strip()
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
    print(f"Found {len(meeting_files)} meeting files to chunk and embed.\n")
    
    all_chunks_rows = []
    
    for idx, filename in enumerate(meeting_files):
        file_path = MEETINGS_DIR / filename
        stem = Path(filename).stem
        json_path = EXTRACTED_DIR / f"{stem}.json"
        
        if not json_path.exists():
            print(f"Skipping meeting {filename} (no extracted metadata JSON found in {EXTRACTED_DIR}).")
            continue
            
        print(f"[{idx+1}/{len(meeting_files)}] Processing Meeting: {filename}")
        
        # Load metadata
        with open(json_path, "r", encoding="utf-8") as f:
            meta_dict = json.load(f)
            meta = ExtractedMeeting(**meta_dict)
            
        # Extract full text
        try:
            if filename.endswith(".md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            elif filename.endswith(".pdf"):
                text = extract_text_from_pdf(file_path)
            else:
                text = extract_text_from_docx(file_path)
        except Exception as e:
            print(f"  Error reading file: {e}")
            continue
            
        # Chunk text (meetings are transcripts/notes)
        chunks = chunk_text(text, is_transcript=True)
        print(f"  Split into {len(chunks)} chunks.")
        
        sentiment = "NEUTRAL"
        from normalize import resolve_name, standardize_date
        attendees = [resolve_name(a) for a in meta.attendees]
        std_date = standardize_date(meta.date)
        
        for c_idx, chunk in enumerate(chunks):
            chunk_id = f"{meta.meetingId}-c{str(c_idx).zfill(3)}"
            
            try:
                vector = generate_embedding(chunk)
                
                all_chunks_rows.append({
                    "chunk_id": chunk_id,
                    "meeting_id": meta.meetingId,
                    "date": std_date,
                    "text": chunk,
                    "attendees": attendees,
                    "topics": meta.topicsDiscussed,
                    "sentiment": sentiment,
                    "embedding": [float(val) for val in vector]
                })
            except Exception as e:
                print(f"  Error embedding chunk {c_idx}: {e}")
                
        if len(all_chunks_rows) >= 50:
            upload_chunks_to_bq(all_chunks_rows)
            all_chunks_rows = []

    # --- Part 2: Process Non-Meeting Documents ---
    EXTRACTED_DOCS_DIR = Path(__file__).resolve().parents[1] / "data" / "extracted_docs"
    
    if EXTRACTED_DOCS_DIR.exists():
        doc_json_files = [f for f in os.listdir(EXTRACTED_DOCS_DIR) if f.endswith(".json")]
        print(f"\nFound {len(doc_json_files)} non-meeting documents to chunk and embed.\n")
        
        for idx, json_filename in enumerate(doc_json_files):
            json_path = EXTRACTED_DOCS_DIR / json_filename
            print(f"[{idx+1}/{len(doc_json_files)}] Processing Document: {json_filename}")
            
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    doc_dict = json.load(f)
                
                text = doc_dict.get("text", "")
                doc_id = doc_dict.get("docId", "")
                date_str = doc_dict.get("date", None)
                authors = doc_dict.get("authors", [])
                topics = doc_dict.get("topics", [])
                
                from normalize import resolve_name, standardize_date
                authors_resolved = [resolve_name(a) for a in authors]
                std_date = standardize_date(date_str)
                
                # Chunk text (documents are not transcripts)
                chunks = chunk_text(text, is_transcript=False)
                print(f"  Split into {len(chunks)} chunks.")
                
                for c_idx, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}-c{str(c_idx).zfill(3)}"
                    try:
                        vector = generate_embedding(chunk)
                        all_chunks_rows.append({
                            "chunk_id": chunk_id,
                            "meeting_id": doc_id,
                            "date": std_date,
                            "text": chunk,
                            "attendees": authors_resolved,
                            "topics": topics,
                            "sentiment": "NEUTRAL",
                            "embedding": [float(val) for val in vector]
                        })
                    except Exception as e:
                        print(f"  Error embedding doc chunk {c_idx}: {e}")
            except Exception as e:
                print(f"  Error processing document JSON {json_filename}: {e}")
                
            if len(all_chunks_rows) >= 50:
                upload_chunks_to_bq(all_chunks_rows)
                all_chunks_rows = []
                
    # Final upload
    if all_chunks_rows:
        upload_chunks_to_bq(all_chunks_rows)

def upload_chunks_to_bq(rows):
    table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), TABLE_ID)
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND
    )
    
    print(f"Uploading {len(rows)} embedding chunks to table '{TABLE_ID}'...")
    try:
        job = bq_client.load_table_from_json(rows, table_ref, job_config=job_config)
        job.result()
        print(f"  Successfully loaded {len(rows)} chunks.")
    except Exception as e:
        print(f"  Error loading embeddings to BigQuery: {e}")

def main():
    print(f"Starting document embedding and indexing pipeline.")
    print(f"GCP Project: {PROJECT_ID}\n")
    
    dataset_ref = bigquery.DatasetReference(PROJECT_ID, DATASET_ID)
    try:
        bq_client.get_dataset(dataset_ref)
    except NotFound:
        print(f"Dataset '{DATASET_ID}' does not exist. Please run warehouse.py first to create it.")
        return
        
    process_and_embed_all()
    print("\nEmbedding and indexing pipeline completed successfully.")

if __name__ == "__main__":
    main()
