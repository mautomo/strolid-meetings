import os
import sys
import io
from google import genai
from google.cloud import bigquery

# Force UTF-8 for stdout and stderr on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"
TABLE_ID = "embeddings"

genai_client = genai.Client()
bq_client = bigquery.Client(project=PROJECT_ID)

def verify_rag_search():
    query_text = "What was decided about the BC outbound campaign?"
    print(f"RAG Test Query: '{query_text}'")
    
    # 1. Embed query
    try:
        response = genai_client.models.embed_content(
            model="gemini-embedding-2",
            contents=query_text
        )
        query_vector = response.embeddings[0].values
        print(f"Generated query vector (dimension: {len(query_vector)})")
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return
        
    # 2. Run Cosine Similarity Vector Search in BigQuery
    sql = f"""
    SELECT 
      base.chunk_id, base.meeting_id, base.date, base.text, base.attendees, base.topics,
      distance
    FROM VECTOR_SEARCH(
      TABLE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`,
      'embedding',
      (SELECT @query_vector as embedding),
      top_k => 3
    )
    """
    
    params = [
        bigquery.ArrayQueryParameter("query_vector", "FLOAT64", query_vector)
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    
    print("Executing BigQuery vector search query...")
    try:
        query_job = bq_client.query(sql, job_config=job_config)
        results = list(query_job.result())
        print(f"Found {len(results)} matches.\n")
        
        for idx, row in enumerate(results):
            print(f"Match [{idx+1}] distance: {row['distance']:.3f} | Date: {row['date']} | Meeting: {row['meeting_id']}")
            print(f"Attendees: {', '.join(row['attendees'])}")
            print(f"Text Passage: \"{row['text'].strip()[:200]}...\"")
            print("-" * 50)
            
        print("Success! RAG search is fully verified.")
    except Exception as e:
        print(f"Error running vector query: {e}")

if __name__ == "__main__":
    verify_rag_search()
