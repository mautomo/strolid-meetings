import os
import sys
import json
from pathlib import Path
from datetime import datetime
from google import genai
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract_text_from_docx
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

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def generate_embedding(text: str) -> list[float]:
    response = genai_client.models.embed_content(
        model="gemini-embedding-2",
        contents=text
    )
    # The API returns values as list of floats
    return response.embeddings[0].values

def process_and_embed_all():
    create_embeddings_table_if_not_exists()
    
    all_files = os.listdir(MEETINGS_DIR)
    meeting_files = [
        f for f in all_files
        if (f.endswith(".docx") or (f.endswith(".md") and "Notes by Gemini" in f))
        and f not in EXCLUDE_FILES
    ]
    
    print(f"Found {len(meeting_files)} files to chunk and embed.\n")
    
    all_chunks_rows = []
    
    for idx, filename in enumerate(meeting_files):
        file_path = MEETINGS_DIR / filename
        stem = Path(filename).stem
        json_path = EXTRACTED_DIR / f"{stem}.json"
        
        if not json_path.exists():
            print(f"Skipping {filename} (no extracted metadata JSON found).")
            continue
            
        print(f"[{idx+1}/{len(meeting_files)}] Processing: {filename}")
        
        # Load metadata
        with open(json_path, "r", encoding="utf-8") as f:
            meta_dict = json.load(f)
            meta = ExtractedMeeting(**meta_dict)
            
        # Extract full text
        try:
            if filename.endswith(".md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            else:
                text = extract_text_from_docx(file_path)
        except Exception as e:
            print(f"  Error reading file: {e}")
            continue
            
        # Chunk text
        chunks = chunk_text(text)
        print(f"  Split into {len(chunks)} chunks.")
        
        # We also want to compute sentiment score for this meeting
        # Simple sentiment mapping
        sentiment = "NEUTRAL"
        # We can extract sentiment label if we want, or default to NEUTRAL.
        # Let's map attendees to standard name resolving
        from normalize import resolve_name
        attendees = [resolve_name(a) for a in meta.attendees]
        
        for c_idx, chunk in enumerate(chunks):
            chunk_id = f"{meta.meetingId}-c{str(c_idx).zfill(3)}"
            
            try:
                # Generate embedding
                vector = generate_embedding(chunk)
                
                all_chunks_rows.append({
                    "chunk_id": chunk_id,
                    "meeting_id": meta.meetingId,
                    "date": meta.date,
                    "text": chunk,
                    "attendees": attendees,
                    "topics": meta.topicsDiscussed,
                    "sentiment": sentiment,
                    "embedding": [float(val) for val in vector]
                })
            except Exception as e:
                print(f"  Error embedding chunk {c_idx}: {e}")
                
        # Batch insert to BigQuery every 5 files to avoid memory overhead
        if len(all_chunks_rows) >= 50:
            upload_chunks_to_bq(all_chunks_rows)
            all_chunks_rows = []
            
    # Final upload
    if all_chunks_rows:
        upload_chunks_to_bq(all_chunks_rows)

def upload_chunks_to_bq(rows):
    table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), TABLE_ID)
    
    # Configure load job
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND # Append chunks
    )
    
    print(f"Uploading {len(rows)} embedding chunks to table '{TABLE_ID}'...")
    try:
        # Since we append, let's make sure we do not duplicate chunks in production.
        # Under normal conditions, WRITE_APPEND adds new records.
        job = bq_client.load_table_from_json(rows, table_ref, job_config=job_config)
        job.result()
        print(f"  Successfully loaded {len(rows)} chunks.")
    except Exception as e:
        print(f"  Error loading embeddings to BigQuery: {e}")

def main():
    print(f"Starting document embedding and indexing pipeline.")
    print(f"GCP Project: {PROJECT_ID}\n")
    
    # Verify dataset exists
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
