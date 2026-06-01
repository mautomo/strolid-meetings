import os
import sys
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema_types import NormalizedData

NORMALIZED_DIR = Path(__file__).resolve().parents[1] / "data" / "normalized"
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"

client = bigquery.Client(project=PROJECT_ID)

def create_dataset_if_not_exists():
    dataset_ref = bigquery.DatasetReference(PROJECT_ID, DATASET_ID)
    try:
        client.get_dataset(dataset_ref)
        print(f"Dataset '{DATASET_ID}' already exists.")
    except NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset)
        print(f"Dataset '{DATASET_ID}' created successfully.")

def define_tables_and_schemas():
    # We define schema arrays for BigQuery tables
    schemas = {
        "meetings": [
            bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("title", "STRING"),
            bigquery.SchemaField("date", "DATE"),
            bigquery.SchemaField("series", "STRING"),
            bigquery.SchemaField("type", "STRING"),
            bigquery.SchemaField("summary", "STRING"),
            bigquery.SchemaField("sentiment_score", "FLOAT64"),
            bigquery.SchemaField("sentiment_label", "STRING"),
            bigquery.SchemaField("tension_score", "FLOAT64"),
            bigquery.SchemaField("attendee_count", "INTEGER")
        ],
        "meeting_attendees": [
            bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("person_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("person_name", "STRING"),
            bigquery.SchemaField("words_spoken", "INTEGER"),
            bigquery.SchemaField("participation_percentage", "FLOAT64"),
            bigquery.SchemaField("level_of_participation", "STRING")
        ],
        "decisions": [
            bigquery.SchemaField("decision_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("decided_by", "STRING", mode="REPEATED"),
            bigquery.SchemaField("meeting_id", "STRING"),
            bigquery.SchemaField("meeting_date", "DATE"),
            bigquery.SchemaField("topic", "STRING"),
            bigquery.SchemaField("confidence", "STRING"),
            bigquery.SchemaField("supersedes", "STRING"),
            bigquery.SchemaField("superseded_by", "STRING")
        ],
        "action_items": [
            bigquery.SchemaField("action_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("task", "STRING"),
            bigquery.SchemaField("owner", "STRING"),
            bigquery.SchemaField("meeting_id", "STRING"),
            bigquery.SchemaField("meeting_date", "DATE"),
            bigquery.SchemaField("deadline", "DATE"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("resolved_in_meeting", "STRING"),
            bigquery.SchemaField("expected_outcome_system", "STRING"),
            bigquery.SchemaField("expected_outcome_description", "STRING")
        ],
        "topics": [
            bigquery.SchemaField("topic_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("label", "STRING"),
            bigquery.SchemaField("first_mentioned", "DATE"),
            bigquery.SchemaField("last_mentioned", "DATE"),
            bigquery.SchemaField("mention_count", "INTEGER")
        ],
        "direction_changes": [
            bigquery.SchemaField("topic", "STRING"),
            bigquery.SchemaField("original_position", "STRING"),
            bigquery.SchemaField("original_date", "DATE"),
            bigquery.SchemaField("original_meeting", "STRING"),
            bigquery.SchemaField("new_position", "STRING"),
            bigquery.SchemaField("change_date", "DATE"),
            bigquery.SchemaField("change_meeting", "STRING"),
            bigquery.SchemaField("days_between", "INTEGER")
        ],
        "person_direction_changes": [
            bigquery.SchemaField("person", "STRING"),
            bigquery.SchemaField("topic", "STRING"),
            bigquery.SchemaField("original_position", "STRING"),
            bigquery.SchemaField("original_date", "DATE"),
            bigquery.SchemaField("original_meeting", "STRING"),
            bigquery.SchemaField("original_confidence", "STRING"),
            bigquery.SchemaField("new_position", "STRING"),
            bigquery.SchemaField("change_date", "DATE"),
            bigquery.SchemaField("change_meeting", "STRING"),
            bigquery.SchemaField("new_confidence", "STRING"),
            bigquery.SchemaField("days_between", "INTEGER")
        ],
        "documents": [
            bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("title", "STRING"),
            bigquery.SchemaField("date", "DATE"),
            bigquery.SchemaField("category", "STRING"),
            bigquery.SchemaField("summary", "STRING"),
            bigquery.SchemaField("sentiment", "STRING"),
            bigquery.SchemaField("sentiment_score", "FLOAT64"),
            bigquery.SchemaField("people_involved", "STRING", mode="REPEATED"),
            bigquery.SchemaField("topics", "STRING", mode="REPEATED")
        ],
        "contributions": [
            bigquery.SchemaField("contribution_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("meeting_date", "DATE"),
            bigquery.SchemaField("person_name", "STRING"),
            bigquery.SchemaField("topic", "STRING"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("type", "STRING"),
            bigquery.SchemaField("occurrence", "STRING"),
            bigquery.SchemaField("status", "STRING")
        ]
    }
    
    for table_name, schema in schemas.items():
        table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), table_name)
        try:
            client.get_table(table_ref)
            print(f"Table '{table_name}' already exists.")
        except NotFound:
            table = bigquery.Table(table_ref, schema=schema)
            # Add time partitioning on DATE field if available
            if table_name in ["meetings", "decisions", "action_items", "contributions", "documents"]:
                partition_field = "date" if table_name in ["meetings", "documents"] else "meeting_date"
                table.time_partitioning = bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
                    field=partition_field
                )
            client.create_table(table)
            print(f"Table '{table_name}' created successfully with schemas.")

def load_data_to_bq(data: NormalizedData):
    # Prepare meetings data
    meetings_rows = []
    attendees_rows = []
    contributions_rows = []
    contribution_counter = 1
    
    for m in data.meetings:
        tension_count = len(m.tensions)
        
        # Calculate a basic sentiment score based on summary content
        summary_lower = m.summary.lower()
        pos_words = ["agree", "success", "align", "good", "progress", "complete", "done"]
        neg_words = ["delay", "tension", "concern", "disagree", "issue", "struggle", "fail"]
        pos_count = sum(1 for w in pos_words if w in summary_lower)
        neg_count = sum(1 for w in neg_words if w in summary_lower)
        
        score = 0.0
        if pos_count + neg_count > 0:
            score = (pos_count - neg_count) / (pos_count + neg_count)
            
        label = "NEUTRAL"
        if score > 0.15:
            label = "POSITIVE"
        elif score < -0.15:
            label = "NEGATIVE"
        elif pos_count > 0 and neg_count > 0:
            label = "MIXED"

        meetings_rows.append({
            "meeting_id": m.meetingId,
            "title": m.title,
            "date": m.date,
            "series": m.series,
            "type": m.type,
            "summary": m.summary,
            "sentiment_score": float(score),
            "sentiment_label": label,
            "tension_score": float(tension_count),
            "attendee_count": len(m.attendees)
        })
        
        # Resolve attendee mapping and participation
        participation_map = {}
        for p in getattr(m, "participation", []):
            participation_map[p.person_name.lower()] = p
            
        for name in m.attendees:
            from normalize import resolve_name, make_person_id
            res_name = resolve_name(name)
            p_id = make_person_id(res_name)
            
            part_info = participation_map.get(res_name.lower())
            words = part_info.words_spoken if part_info else 0
            pct = part_info.participation_percentage if part_info else 0.0
            level = part_info.level if part_info else "NONE"
            
            attendees_rows.append({
                "meeting_id": m.meetingId,
                "person_id": p_id,
                "person_name": res_name,
                "words_spoken": int(words),
                "participation_percentage": float(pct),
                "level_of_participation": level
            })
            
        # Parse contributions
        meeting_contributions = getattr(m, "contributions", [])
        for c in meeting_contributions:
            from normalize import resolve_name
            contributions_rows.append({
                "contribution_id": f"c-{str(contribution_counter).zfill(3)}",
                "meeting_id": m.meetingId,
                "meeting_date": m.date,
                "person_name": resolve_name(c.person_name),
                "topic": c.topic,
                "description": c.description,
                "type": c.type,
                "occurrence": c.occurrence,
                "status": c.status
            })
            contribution_counter += 1
            
    # Decisions rows
    decisions_rows = []
    for d in data.decisions:
        decisions_rows.append({
            "decision_id": d.id,
            "description": d.description,
            "decided_by": d.decidedBy,
            "meeting_id": d.meetingId,
            "meeting_date": d.meetingDate,
            "topic": d.topic,
            "confidence": d.confidence,
            "supersedes": d.supersedes or None,
            "superseded_by": d.supersededBy or None
        })
        
    # Action items rows
    actions_rows = []
    for ai in data.actionItems:
        actions_rows.append({
            "action_id": ai.id,
            "task": ai.task,
            "owner": ai.owner,
            "meeting_id": ai.meetingId,
            "meeting_date": ai.meetingDate,
            "deadline": ai.deadline or None,
            "status": ai.status,
            "resolved_in_meeting": ai.resolvedInMeeting or None,
            "expected_outcome_system": ai.expectedOutcome.system if ai.expectedOutcome else None,
            "expected_outcome_description": ai.expectedOutcome.description if ai.expectedOutcome else None
        })
        
    # Topics rows
    topics_rows = []
    for t in data.topics:
        topics_rows.append({
            "topic_id": t.id,
            "label": t.label,
            "first_mentioned": t.firstMentioned,
            "last_mentioned": t.lastMentioned,
            "mention_count": t.mentionCount
        })
        
    # Direction changes
    changes_rows = []
    for c in data.directionChanges:
        changes_rows.append({
            "topic": c.topic,
            "original_position": c.originalPosition,
            "original_date": c.originalDate,
            "original_meeting": c.originalMeeting,
            "new_position": c.newPosition,
            "change_date": c.changeDate,
            "change_meeting": c.changeMeeting,
            "days_between": c.daysBetween
        })

    # Per-person direction reversals
    person_changes_rows = []
    for c in data.personDirectionChanges:
        person_changes_rows.append({
            "person": c.person,
            "topic": c.topic,
            "original_position": c.originalPosition,
            "original_date": c.originalDate,
            "original_meeting": c.originalMeeting,
            "original_confidence": c.originalConfidence,
            "new_position": c.newPosition,
            "change_date": c.changeDate,
            "change_meeting": c.changeMeeting,
            "new_confidence": c.newConfidence,
            "days_between": c.daysBetween
        })
        
    # Load Document metadata from extracted_docs/
    EXTRACTED_DOCS_DIR = Path(__file__).resolve().parents[1] / "data" / "extracted_docs"
    documents_rows = []
    if EXTRACTED_DOCS_DIR.exists():
        for file in os.listdir(EXTRACTED_DOCS_DIR):
            if not file.endswith(".json"):
                continue
            try:
                with open(EXTRACTED_DOCS_DIR / file, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    from normalize import resolve_name
                    documents_rows.append({
                        "doc_id": doc["docId"],
                        "title": doc["title"],
                        "date": doc.get("date"),
                        "category": doc.get("category", "other"),
                        "summary": doc["summary"],
                        "sentiment": doc.get("sentiment", "neutral"),
                        "sentiment_score": float(doc.get("sentimentScore", 0.0)),
                        "people_involved": [resolve_name(p) for p in doc.get("peopleInvolved", doc.get("authors", []))],
                        "topics": doc.get("topics", [])
                    })
            except Exception as e:
                print(f"Error loading document JSON {file}: {e}")

    # Upload each table using BigQuery Client load_table_from_json
    tables_data = {
        "meetings": meetings_rows,
        "meeting_attendees": attendees_rows,
        "decisions": decisions_rows,
        "action_items": actions_rows,
        "topics": topics_rows,
        "direction_changes": changes_rows,
        "person_direction_changes": person_changes_rows,
        "documents": documents_rows,
        "contributions": contributions_rows
    }
    
    for table_name, rows in tables_data.items():
        if not rows:
            print(f"No rows to insert for {table_name}.")
            continue
            
        table_ref = bigquery.TableReference(bigquery.DatasetReference(PROJECT_ID, DATASET_ID), table_name)
        
        # Configure load job
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE # Overwrite each upload
        )
        
        print(f"Uploading {len(rows)} rows to table '{table_name}'...")
        try:
            job = client.load_table_from_json(rows, table_ref, job_config=job_config)
            job.result() # Wait for completion
            print(f"  Successfully loaded '{table_name}'.")
        except Exception as e:
            print(f"  Error loading '{table_name}': {e}")

def main():
    # Load normalized combined data
    all_json_path = NORMALIZED_DIR / "all.json"
    if not all_json_path.exists():
        print(f"Error: Normalized data file not found at {all_json_path}. Please run normalize.py first.")
        return
        
    with open(all_json_path, "r", encoding="utf-8") as f:
        data_dict = json.load(f)
        data = NormalizedData(**data_dict)
        
    print(f"Initializing warehouse in Google Cloud Project: {PROJECT_ID}\n")
    create_dataset_if_not_exists()
    define_tables_and_schemas()
    print()
    load_data_to_bq(data)
    print("\nWarehouse ingestion completed successfully.")

if __name__ == "__main__":
    main()
