import os
import sys
import json
from pathlib import Path
from google import genai
from google.cloud import bigquery
from google.adk.agents import Agent

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "meeting-analysis-496916")
DATASET_ID = "strolid_meetings"

genai_client = genai.Client()
bq_client = bigquery.Client(project=PROJECT_ID)

async def rag_search(
    query: str,
    attendees: list[str] = None,
    start_date: str = None,
    end_date: str = None,
    topics: list[str] = None
) -> str:
    """Perform a vector-based semantic search over meeting transcripts and summaries.
    
    Supports filtering search results by date range, specific individuals, and topics.
    
    Args:
        query: Semantic query text (e.g. "What did Michael say about website launch delays?").
        attendees: Optional list of names of individuals who attended (e.g. ["Vinnie Micciche", "Michael Donovan"]).
        start_date: Optional start date filter in YYYY-MM-DD format (inclusive).
        end_date: Optional end date filter in YYYY-MM-DD format (inclusive).
        topics: Optional list of kebab-case topics discussed (e.g. ["website-refresh", "messaging-strategy"]).
        
    Returns:
        A text report containing the top matched transcript passages.
    """
    try:
        # Generate embedding for the query
        response = genai_client.models.embed_content(
            model="gemini-embedding-2",
            contents=query
        )
        query_vector = response.embeddings[0].values
        
        # Build query filters
        filters = []
        params = [bigquery.ArrayQueryParameter("query_vector", "FLOAT64", query_vector)]
        
        if start_date:
            filters.append("date >= @start_date")
            params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start_date))
        if end_date:
            filters.append("date <= @end_date")
            params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end_date))
        if attendees:
            filters.append("EXISTS (SELECT 1 FROM UNNEST(attendees) a WHERE a IN UNNEST(@attendees))")
            params.append(bigquery.ArrayQueryParameter("attendees", "STRING", attendees))
        if topics:
            filters.append("EXISTS (SELECT 1 FROM UNNEST(topics) t WHERE t IN UNNEST(@topics))")
            params.append(bigquery.ArrayQueryParameter("topics", "STRING", topics))
            
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        
        sql_query = f"""
        SELECT 
          chunk_id, meeting_id, date, text, attendees, topics,
          VECTOR_DISTANCE(embedding, @query_vector, 'COSINE') as distance
        FROM `{PROJECT_ID}.{DATASET_ID}.embeddings`
        {where_clause}
        ORDER BY distance ASC
        LIMIT 5
        """
        
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        query_job = bq_client.query(sql_query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            return "No matching meeting segments found for your query with those filters."
            
        output = [f"Top semantic matches in the transcript repository for query: '{query}'\n"]
        for idx, row in enumerate(results):
            similarity = 1.0 - row["distance"]
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
            output.append(
                f"[{idx+1}] Meeting: {row['meeting_id']} | Date: {date_str} | Similarity: {similarity:.2f}\n"
                f"Attendees: {', '.join(row['attendees'])}\n"
                f"Topics: {', '.join(row['topics'])}\n"
                f"Passage:\n\"\"\"\n{row['text'].strip()}\n\"\"\"\n"
                + "-" * 40
            )
        return "\n".join(output)
    except Exception as e:
        return f"Error executing RAG search: {e}"

async def get_analytics_summary(
    individual_name: str = None,
    topic: str = None,
    start_date: str = None,
    end_date: str = None
) -> str:
    """Query the relational data warehouse to fetch quantitative meeting analytics,
    sentiment records, and calculate performance/relationship scores.
    
    Args:
        individual_name: Optional name of person to analyze (e.g. "Vinnie Micciche").
        topic: Optional kebab-case topic to analyze (e.g. "messaging-strategy").
        start_date: Optional start date filter in YYYY-MM-DD.
        end_date: Optional end date filter in YYYY-MM-DD.
        
    Returns:
        A text report of analytics metrics, scores, and relationship trends.
    """
    try:
        # Build where clauses for tables
        filters = []
        params = []
        
        if start_date:
            filters.append("date >= @start_date")
            params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start_date))
        if end_date:
            filters.append("date <= @end_date")
            params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end_date))
            
        where_meetings = f"WHERE {' AND '.join(filters)}" if filters else ""
        
        # 1. Total meetings & sentiment stats
        sql_meetings = f"""
        SELECT 
          COUNT(*) as total_meetings,
          AVG(sentiment_score) as avg_sentiment,
          SUM(tension_score) as total_tensions
        FROM `{PROJECT_ID}.{DATASET_ID}.meetings`
        {where_meetings}
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[p for p in params]
        )
        job = bq_client.query(sql_meetings, job_config=job_config)
        meetings_stats = list(job.result())[0]
        
        tot_meetings = meetings_stats["total_meetings"] or 0
        avg_sentiment = meetings_stats["avg_sentiment"] or 0.0
        tot_tensions = meetings_stats["total_tensions"] or 0.0
        
        # 2. Decision statistics
        decisions_filters = []
        decisions_params = []
        if start_date:
            decisions_filters.append("meeting_date >= @start_date")
            decisions_params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start_date))
        if end_date:
            decisions_filters.append("meeting_date <= @end_date")
            decisions_params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end_date))
            
        if individual_name:
            decisions_filters.append("@individual IN UNNEST(decided_by)")
            decisions_params.append(bigquery.ScalarQueryParameter("individual", "STRING", individual_name))
        if topic:
            normalized_topic = topic.strip().lower().replace(" ", "-")
            decisions_filters.append("topic LIKE @topic")
            decisions_params.append(bigquery.ScalarQueryParameter("topic", "STRING", f"%{normalized_topic}%"))
            
        where_decisions = f"WHERE {' AND '.join(decisions_filters)}" if decisions_filters else ""
        sql_decisions = f"""
        SELECT 
          COUNT(*) as total_decisions,
          SUM(CASE WHEN supersedes IS NOT NULL THEN 1 ELSE 0 END) as strategic_shifts,
          SUM(CASE WHEN confidence = 'firm' THEN 1 ELSE 0 END) as firm_decisions
        FROM `{PROJECT_ID}.{DATASET_ID}.decisions`
        {where_decisions}
        """
        job_config = bigquery.QueryJobConfig(query_parameters=decisions_params)
        job = bq_client.query(sql_decisions, job_config=job_config)
        decisions_stats = list(job.result())[0]
        
        tot_decisions = decisions_stats["total_decisions"] or 0
        shifts = decisions_stats["strategic_shifts"] or 0
        firm = decisions_stats["firm_decisions"] or 0
        
        # 3. Action items statistics
        action_filters = []
        action_params = []
        if start_date:
            action_filters.append("meeting_date >= @start_date")
            action_params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start_date))
        if end_date:
            action_filters.append("meeting_date <= @end_date")
            action_params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end_date))
            
        if individual_name:
            action_filters.append("owner = @individual")
            action_params.append(bigquery.ScalarQueryParameter("individual", "STRING", individual_name))
        where_actions = f"WHERE {' AND '.join(action_filters)}" if action_filters else ""
        sql_actions = f"""
        SELECT 
          COUNT(*) as total_actions,
          SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done_actions,
          SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END) as abandoned_actions,
          SUM(CASE WHEN status = 'recurring' THEN 1 ELSE 0 END) as recurring_actions,
          SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_actions
        FROM `{PROJECT_ID}.{DATASET_ID}.action_items`
        {where_actions}
        """
        job_config = bigquery.QueryJobConfig(query_parameters=action_params)
        job = bq_client.query(sql_actions, job_config=job_config)
        actions_stats = list(job.result())[0]
        
        tot_actions = actions_stats["total_actions"] or 0
        done_actions = actions_stats["done_actions"] or 0
        abandoned_actions = actions_stats["abandoned_actions"] or 0
        recurring_actions = actions_stats["recurring_actions"] or 0
        open_actions = actions_stats["open_actions"] or 0
        
        # Calculate Reliability Score
        reliability = (done_actions / tot_actions * 100) if tot_actions > 0 else 0.0
        
        # Format Report
        report = []
        title_str = "SYSTEM ANALYSIS SCORECARD"
        if individual_name:
            title_str += f" FOR {individual_name.upper()}"
        if topic:
            title_str += f" (TOPIC: {topic.upper()})"
            
        report.append(f"=== {title_str} ===")
        report.append(f"Total Meetings Attended/Analyzed: {tot_meetings}")
        report.append(f"Average Meeting Sentiment Score: {avg_sentiment:.2f} (Scale: -1.0 to 1.0)")
        report.append(f"Total Tension Incidents Recorded: {tot_tensions}")
        
        report.append("\n--- Decision Logging ---")
        report.append(f"Decisions Registered: {tot_decisions}")
        report.append(f"  Firm Commitments: {firm}")
        report.append(f"  Strategic Trajectory Shifts: {shifts}")
        if tot_decisions > 0:
            report.append(f"  Decision Firmness Rate: {(firm/tot_decisions*100):.1f}%")
            
        report.append("\n--- Action Item Scorecard ---")
        report.append(f"Action Items Assigned: {tot_actions}")
        report.append(f"  Completed: {done_actions}")
        report.append(f"  Open: {open_actions}")
        report.append(f"  Abandoned: {abandoned_actions}")
        report.append(f"  Recurring (Delayed): {recurring_actions}")
        report.append(f"Reliability (Completion Rate): {reliability:.1f}%")
        
        # Add topic scoring analysis if topic is selected
        if topic:
            # Topic zombie analysis
            zombie_score = "LOW"
            if tot_meetings >= 4 and firm == 0:
                zombie_score = "HIGH (Discussed repeatedly with no resolution)"
            elif tot_meetings >= 3 and firm == 0:
                zombie_score = "MEDIUM"
            report.append(f"\n--- Topic Assessment ---")
            report.append(f"Topic: {topic}")
            report.append(f"Strategic Instability Score (Shifts): {shifts}")
            report.append(f"Zombie Status: {zombie_score}")
            
        return "\n".join(report)
    except Exception as e:
        return f"Error executing analytics: {e}"

async def generate_presentation_artifact(
    title: str,
    subtitle: str,
    slide_titles: list[str],
    slide_contents: list[str]
) -> str:
    """Generate a structured presentation JSON payload to display slide content in the UI.
    
    The backend stores this artifact in the Firestore session for the frontend React client.
    
    Args:
        title: Main presentation title.
        subtitle: Subtitle or context.
        slide_titles: List of titles for each slide.
        slide_contents: List of detailed paragraph contents/bullets for each slide.
        
    Returns:
        A JSON confirmation string containing the presentation artifact configuration.
    """
    slides = []
    # Add title slide
    slides.append({
        "id": "slide-title",
        "layout": "hero",
        "title": title,
        "subtitle": subtitle,
        "bullets": []
    })
    
    for idx, (t, c) in enumerate(zip(slide_titles, slide_contents)):
        # Split content into bullet points
        bullets = [b.strip("- ") for b in c.split("\n") if b.strip()]
        slides.append({
            "id": f"slide-{idx+1}",
            "layout": "bullets" if len(bullets) > 1 else "paragraphs",
            "title": t,
            "subtitle": "",
            "bullets": bullets
        })
        
    artifact = {
        "artifact_type": "presentation",
        "title": title,
        "theme": "dark-morphism",
        "slides": slides
    }
    
    return json.dumps(artifact, indent=2)

async def generate_timeline_artifact(
    title: str,
    topic: str = None,
    start_date: str = None,
    end_date: str = None
) -> str:
    """Query Decisions, Actions, and Tensions chronologically and build a structured timeline UI payload.
    
    Args:
        title: Title of the timeline.
        topic: Optional kebab-case topic to limit timeline items.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        
    Returns:
        A JSON confirmation string containing the timeline events array.
    """
    try:
        decisions_filters = []
        params = []
        
        if start_date:
            decisions_filters.append("meeting_date >= @start_date")
            params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start_date))
        if end_date:
            decisions_filters.append("meeting_date <= @end_date")
            params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end_date))
        if topic:
            decisions_filters.append("topic = @topic")
            params.append(bigquery.ScalarQueryParameter("topic", "STRING", topic))
            
        where = f"WHERE {' AND '.join(decisions_filters)}" if decisions_filters else ""
        
        sql = f"""
        SELECT 
          meeting_date as date, 'decision' as type, description as summary, 
          ARRAY_TO_STRING(decided_by, ', ') as detail, meeting_id
        FROM `{PROJECT_ID}.{DATASET_ID}.decisions`
        {where}
        
        UNION ALL
        
        SELECT 
          meeting_date as date, 'action_item' as type, task as summary,
          CONCAT('Owner: ', owner, ' | Status: ', status) as detail, meeting_id
        FROM `{PROJECT_ID}.{DATASET_ID}.action_items`
        {where.replace("meeting_date", "meeting_date")} -- adjust field names if needed
        
        ORDER BY date ASC
        """
        
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        job = bq_client.query(sql, job_config=job_config)
        results = list(job.result())
        
        events = []
        for idx, row in enumerate(results):
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
            events.append({
                "id": f"evt-{idx+1}",
                "date": date_str,
                "type": row["type"],
                "summary": row["summary"],
                "details": row["detail"],
                "meeting_id": row["meeting_id"]
            })
            
        artifact = {
            "artifact_type": "timeline",
            "title": title,
            "events": events
        }
        
        return json.dumps(artifact, indent=2)
    except Exception as e:
        return f"Error compiling timeline artifact: {e}"

def build_agent() -> Agent:
    instruction = (
        "You are the Strolid Meeting Intelligence Assistant, a strategic chatbot "
        "designed to help teams review meeting transcripts, analyze relationship dynamics, "
        "and track commitments.\n\n"
        "You have access to tools:\n"
        "1. `rag_search` to query semantic meeting transcripts. ALWAYS use this when asked about "
        "what people said, debates, transcript specifics, or historical context.\n"
        "2. `get_analytics_summary` to pull meeting counts, decision ratios, and reliability statistics "
        "from the data warehouse.\n"
        "3. `generate_presentation_artifact` to create structured presentation slide decks for the user.\n"
        "4. `generate_timeline_artifact` to create chronological event timelines.\n\n"
        "When the user asks to compile a timeline or slide presentation, call the corresponding "
        "artifact tool. Emissary payloads will be picked up by the UI React client to display cards."
    )
    
    return Agent(
        name="meetings_agent",
        model="gemini-2.0-flash", # ADK 2.0 uses gemini-2.0-flash by default
        description="Strolid Meeting Intelligence and scoring assistant.",
        instruction=instruction,
        tools=[rag_search, get_analytics_summary, generate_presentation_artifact, generate_timeline_artifact],
    )
