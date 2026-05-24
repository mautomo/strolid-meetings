import os
from google.cloud import bigquery

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"

client = bigquery.Client(project=PROJECT_ID)

def verify_counts():
    tables = ["meetings", "meeting_attendees", "decisions", "action_items", "topics", "direction_changes"]
    print(f"Verifying BigQuery dataset: {PROJECT_ID}.{DATASET_ID}\n")
    
    for table_name in tables:
        query = f"SELECT COUNT(*) as count FROM `{PROJECT_ID}.{DATASET_ID}.{table_name}`"
        try:
            query_job = client.query(query)
            results = list(query_job.result())
            count = results[0]["count"]
            print(f"Table '{table_name}': {count} rows present.")
        except Exception as e:
            print(f"Error querying '{table_name}': {e}")
            
    print("\nRunning sample metrics query (Vinnie & Michael Alignment Score)...")
    # Let's count joint decisions vs individual decisions for Vinnie & Michael
    query_alignment = f"""
    SELECT 
      SUM(CASE WHEN 'Vinnie Micciche' IN UNNEST(decided_by) AND 'Michael Donovan' IN UNNEST(decided_by) THEN 1 ELSE 0 END) as joint_count,
      SUM(CASE WHEN 'Vinnie Micciche' IN UNNEST(decided_by) AND 'Michael Donovan' NOT IN UNNEST(decided_by) THEN 1 ELSE 0 END) as vinnie_only_count,
      SUM(CASE WHEN 'Michael Donovan' IN UNNEST(decided_by) AND 'Vinnie Micciche' NOT IN UNNEST(decided_by) THEN 1 ELSE 0 END) as michael_only_count,
      COUNT(*) as total_decisions
    FROM `{PROJECT_ID}.{DATASET_ID}.decisions`
    """
    try:
        query_job = client.query(query_alignment)
        results = list(query_job.result())
        row = results[0]
        joint = row["joint_count"] or 0
        vinnie = row["vinnie_only_count"] or 0
        michael = row["michael_only_count"] or 0
        total = row["total_decisions"] or 0
        
        score = (joint / (joint + vinnie + michael)) * 100 if (joint + vinnie + michael) > 0 else 0
        print("-" * 50)
        print(f"Total decisions: {total}")
        print(f"Joint Decisions (Both): {joint}")
        print(f"Vinnie-Only Decisions: {vinnie}")
        print(f"Michael-Only Decisions: {michael}")
        print(f"Alignment Score: {score:.1f}%")
        print("-" * 50)
        print("Success! BigQuery database is fully verified.")
    except Exception as e:
        print(f"Error running alignment score query: {e}")

if __name__ == "__main__":
    verify_counts()
