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
    topics: list[str] = None,
    meeting_ids: list[str] = None
) -> str:
    """Perform a vector-based semantic search over meeting transcripts and summaries.
    
    Supports filtering search results by date range, specific individuals, topics, and specific meeting IDs.
    
    Args:
        query: Semantic query text (e.g. "What did Michael say about website launch delays?").
        attendees: Optional list of names of individuals who attended (e.g. ["Vinnie Micciche", "Michael Donovan"]).
        start_date: Optional start date filter in YYYY-MM-DD format (inclusive).
        end_date: Optional end date filter in YYYY-MM-DD format (inclusive).
        topics: Optional list of kebab-case topics discussed (e.g. ["website-refresh", "messaging-strategy"]).
        meeting_ids: Optional list of specific meeting IDs to search within.
        
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
        if meeting_ids:
            filters.append("meeting_id IN UNNEST(@meeting_ids)")
            params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
            
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        
        # If there are filters, pre-filter the table
        if where_clause:
            table_expr = f"(SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.embeddings` {where_clause})"
        else:
            table_expr = f"`{PROJECT_ID}.{DATASET_ID}.embeddings`"
            
        sql_query = f"""
        SELECT 
          base.chunk_id as chunk_id, 
          base.meeting_id as meeting_id, 
          base.date as date, 
          base.text as text, 
          base.attendees as attendees, 
          base.topics as topics,
          distance
        FROM VECTOR_SEARCH(
          {table_expr},
          'embedding',
          (SELECT @query_vector as embedding),
          top_k => 5
        )
        """
        
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        query_job = bq_client.query(sql_query, job_config=job_config)
        results = list(query_job.result())
        
        # Filter results by similarity score >= 0.55
        # VECTOR_SEARCH distance for COSINE is cosine distance (1 - cosine similarity).
        filtered_results = []
        for row in results:
            similarity = 1.0 - row["distance"]
            if similarity >= 0.55:
                filtered_results.append((row, similarity))
        
        if not filtered_results:
            return "No matching meeting segments found for your query with those filters."
            
        output = [f"Top semantic matches in the transcript repository for query: '{query}'\n"]
        for idx, (row, similarity) in enumerate(filtered_results):
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") and row["date"] else str(row["date"])
            output.append(
                f"[{idx+1}] Meeting: {row['meeting_id']} | Date: {date_str} | Similarity: {similarity:.2f}\n"
                f"Attendees: {', '.join(row['attendees'])}\n"
                f"Topics: {', '.join(row['topics'])}\n"
                f"Passage:\n\"\"\"\n{row['text'].strip()}\n\"\"\"\n"
                + "-" * 40
            )
        return "\n".join(output)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error executing RAG search: {e}")
        return f"Error executing RAG search: {e}"

async def get_analytics_summary(
    individual_name: str = None,
    topic: str = None,
    start_date: str = None,
    end_date: str = None,
    meeting_ids: list[str] = None
) -> str:
    """Query the relational data warehouse to fetch quantitative meeting analytics,
    sentiment records, and calculate performance/relationship scores.
    
    Args:
        individual_name: Optional name of person to analyze (e.g. "Vinnie Micciche").
        topic: Optional kebab-case topic to analyze (e.g. "messaging-strategy").
        start_date: Optional start date filter in YYYY-MM-DD.
        end_date: Optional end date filter in YYYY-MM-DD.
        meeting_ids: Optional list of specific meeting IDs to restrict analysis.
        
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
        if meeting_ids:
            filters.append("meeting_id IN UNNEST(@meeting_ids)")
            params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
            
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
        if meeting_ids:
            decisions_filters.append("meeting_id IN UNNEST(@meeting_ids)")
            decisions_params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
            
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
        if meeting_ids:
            action_filters.append("meeting_id IN UNNEST(@meeting_ids)")
            action_params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
            
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

async def get_performance_report(
    scope: str,
    timeframe: str = None,
    metrics: list[str] = None,
    meeting_ids: list[str] = None
) -> str:
    """Analyze execution metrics (short, mid, and long-term) and company performance trends
    using data from contributions, action items, decisions, and document metadata.
    
    Args:
        scope: Either 'plan_execution' or 'company_performance'.
        timeframe: Optional timeframe filter: 'short-term', 'mid-term', 'long-term', or 'all'.
        metrics: Optional list of specific metrics to analyze: 'revenue', 'marketing', 'operations', 'churn', 'speed-to-market'.
        meeting_ids: Optional list of specific meeting IDs to restrict analysis.
        
    Returns:
        A report summarizing the performance trends, contributions, and execution scorecard.
    """
    try:
        # Reference date for timeframes is 2026-05-25 based on metadata
        # Short-term: >= 2026-04-25
        # Mid-term: between 2026-02-25 and 2026-04-25
        # Long-term: < 2026-02-25
        date_filter = ""
        if timeframe == "short-term":
            date_filter = "AND {field} >= '2026-04-25'"
        elif timeframe == "mid-term":
            date_filter = "AND {field} >= '2026-02-25' AND {field} < '2026-04-25'"
        elif timeframe == "long-term":
            date_filter = "AND {field} < '2026-02-25'"

        report_lines = []
        
        # Build query params if meeting_ids are supplied
        params = []
        if meeting_ids:
            params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
        job_config = bigquery.QueryJobConfig(query_parameters=params) if params else None
        
        if scope == "plan_execution":
            report_lines.append("=== STRATEGIC PLAN EXECUTION REPORT ===")
            if timeframe:
                report_lines.append(f"Timeframe: {timeframe.upper()}")
            report_lines.append("")

            # 1. Action Items completion rates
            ai_date_filter = date_filter.format(field="meeting_date")
            ai_meeting_filter = "AND meeting_id IN UNNEST(@meeting_ids)" if meeting_ids else ""
            sql_actions = f"""
            SELECT 
              status, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET_ID}.action_items`
            WHERE 1=1 {ai_date_filter} {ai_meeting_filter}
            GROUP BY status
            """
            job = bq_client.query(sql_actions, job_config=job_config)
            actions_data = {row["status"]: row["count"] for row in job.result()}
            
            total_actions = sum(actions_data.values())
            completed = actions_data.get("done", 0)
            open_items = actions_data.get("open", 0)
            delayed = actions_data.get("recurring", 0)
            abandoned = actions_data.get("abandoned", 0)
            
            completion_rate = (completed / total_actions * 100) if total_actions > 0 else 0.0
            
            report_lines.append("--- Action Item Execution ---")
            report_lines.append(f"Total Actions Assigned: {total_actions}")
            report_lines.append(f"  Completed: {completed} ({completion_rate:.1f}%)")
            report_lines.append(f"  Open/In Progress: {open_items}")
            report_lines.append(f"  Recurring/Delayed (Zombie/delayed loops): {delayed}")
            report_lines.append(f"  Abandoned: {abandoned}")
            report_lines.append("")

            # 2. Contributions and Lifecycle
            contrib_date_filter = date_filter.format(field="meeting_date")
            contrib_meeting_filter = "AND meeting_id IN UNNEST(@meeting_ids)" if meeting_ids else ""
            sql_contribs = f"""
            SELECT 
              occurrence, status, COUNT(*) as count
            FROM `{PROJECT_ID}.{DATASET_ID}.contributions`
            WHERE 1=1 {contrib_date_filter} {contrib_meeting_filter}
            GROUP BY occurrence, status
            """
            job = bq_client.query(sql_contribs, job_config=job_config)
            contribs = list(job.result())
            
            first_time_count = sum(row["count"] for row in contribs if row["occurrence"] == "first time")
            repeated_count = sum(row["count"] for row in contribs if row["occurrence"] == "repeated")
            
            approved = sum(row["count"] for row in contribs if row["status"] == "approved")
            denied = sum(row["count"] for row in contribs if row["status"] == "denied")
            success = sum(row["count"] for row in contribs if row["status"] == "completed-success")
            pending = sum(row["count"] for row in contribs if row["status"] in ["proposed", "pending"])
            
            report_lines.append("--- Contribution Lifecycle ---")
            report_lines.append(f"First-time Contributions: {first_time_count}")
            report_lines.append(f"Repeated/Revisited Topics: {repeated_count}")
            report_lines.append("Status Breakdown:")
            report_lines.append(f"  Approved/Accepted: {approved}")
            report_lines.append(f"  Denied/Rejected: {denied}")
            report_lines.append(f"  Completed with Success: {success}")
            report_lines.append(f"  Pending/Proposed: {pending}")
            report_lines.append("")

            # 3. Decisions
            decisions_meeting_filter = "AND meeting_id IN UNNEST(@meeting_ids)" if meeting_ids else ""
            sql_decisions = f"""
            SELECT 
              meeting_date, description, topic, confidence
            FROM `{PROJECT_ID}.{DATASET_ID}.decisions`
            WHERE 1=1 {ai_date_filter} {decisions_meeting_filter}
            ORDER BY meeting_date DESC
            LIMIT 5
            """
            job = bq_client.query(sql_decisions, job_config=job_config)
            decisions = list(job.result())
            
            report_lines.append("--- Key Decisions & Trajectory ---")
            if decisions:
                for idx, d in enumerate(decisions):
                    date_str = d["meeting_date"].strftime("%Y-%m-%d") if hasattr(d["meeting_date"], "strftime") else str(d["meeting_date"])
                    report_lines.append(f"[{idx+1}] {date_str} | Topic: {d['topic']} ({d['confidence']})")
                    report_lines.append(f"    Decision: {d['description']}")
            else:
                report_lines.append("No decisions recorded in this timeframe.")
                
        elif scope == "company_performance":
            report_lines.append("=== COMPANY PERFORMANCE ANALYSIS ===")
            if metrics:
                report_lines.append(f"Selected Areas: {', '.join(metrics).upper()}")
            report_lines.append("")
            
            doc_date_filter = date_filter.format(field="date")
            metric_clauses = []
            if metrics:
                for m in metrics:
                    m_lower = m.lower().strip()
                    metric_clauses.append(f"LOWER(topics_str) LIKE '%{m_lower}%' OR LOWER(category) LIKE '%{m_lower}%'")
            
            metric_filter = f"AND ({' OR '.join(metric_clauses)})" if metric_clauses else ""
            
            sql_docs = f"""
            WITH doc_topics AS (
              SELECT *, ARRAY_TO_STRING(topics, ', ') as topics_str
              FROM `{PROJECT_ID}.{DATASET_ID}.documents`
            )
            SELECT 
              title, date, category, summary, sentiment, sentiment_score
            FROM doc_topics
            WHERE 1=1 {doc_date_filter} {metric_filter}
            ORDER BY date DESC
            LIMIT 6
            """
            job = bq_client.query(sql_docs)
            docs = list(job.result())
            
            avg_score = sum(d["sentiment_score"] for d in docs) / len(docs) if docs else 0.0
            
            report_lines.append("--- Document Intelligence Summary ---")
            report_lines.append(f"Documents Analyzed: {len(docs)}")
            report_lines.append(f"Average Sentiment Score: {avg_score:.2f}")
            report_lines.append("")
            
            report_lines.append("--- Performance Area Details ---")
            if docs:
                for idx, d in enumerate(docs):
                    d_date = d["date"].strftime("%Y-%m-%d") if d["date"] else "N/A"
                    report_lines.append(f"[{idx+1}] {d['title']} | Date: {d_date} | Category: {d['category']}")
                    report_lines.append(f"    Sentiment: {d['sentiment'].upper()} (Score: {d['sentiment_score']:.2f})")
                    report_lines.append(f"    Summary: {d['summary']}")
                    report_lines.append("")
            else:
                report_lines.append("No performance documents match the selected filters.")

            # Related meetings
            meeting_date_filter = date_filter.format(field="date")
            meeting_meeting_filter = "AND meeting_id IN UNNEST(@meeting_ids)" if meeting_ids else ""
            sql_meetings = f"""
            SELECT 
              title, date, summary, sentiment_score, sentiment_label
            FROM `{PROJECT_ID}.{DATASET_ID}.meetings`
            WHERE 1=1 {meeting_date_filter} {meeting_meeting_filter}
            ORDER BY date DESC
            LIMIT 3
            """
            job = bq_client.query(sql_meetings, job_config=job_config)
            meetings = list(job.result())
            
            if meetings:
                report_lines.append("--- Related Meeting Insights ---")
                for m in meetings:
                    m_date = m["date"].strftime("%Y-%m-%d") if hasattr(m["date"], "strftime") else str(m["date"])
                    report_lines.append(f"- {m_date} | {m['title']} (Sentiment: {m['sentiment_label']})")
                    report_lines.append(f"  Summary: {m['summary']}")
                    report_lines.append("")
                    
        return "\n".join(report_lines)
    except Exception as e:
        return f"Error compiling performance report: {e}"

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
    end_date: str = None,
    meeting_ids: list[str] = None
) -> str:
    """Query Decisions, Actions, and Tensions chronologically and build a structured timeline UI payload.
    
    Args:
        title: Title of the timeline.
        topic: Optional kebab-case topic to limit timeline items.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        meeting_ids: Optional list of specific meeting IDs to restrict timeline items.
        
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
        if meeting_ids:
            decisions_filters.append("meeting_id IN UNNEST(@meeting_ids)")
            params.append(bigquery.ArrayQueryParameter("meeting_ids", "STRING", meeting_ids))
            
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

async def generate_scorecard_artifact(
    title: str,
    target: str,
    reliability: float,
    completed_count: int,
    open_count: int,
    delayed_count: int,
    abandoned_count: int,
    top_topics: list[str],
    key_insights: list[str]
) -> str:
    """Generate a structured reliability scorecard JSON payload to display in the Canvas UI.
    
    Use this when the user asks for a scorecard, performance review, or detailed reliability analysis of a person or a topic.
    
    Args:
        title: Title of the scorecard (e.g. "Vinnie Micciche Performance Scorecard").
        target: The name of the person or topic (e.g. "Vinnie Micciche").
        reliability: Reliability score percentage (completion rate, e.g. 85.5).
        completed_count: Count of completed action items.
        open_count: Count of open action items.
        delayed_count: Count of delayed/recurring action items.
        abandoned_count: Count of abandoned action items.
        top_topics: List of key topics associated with this entity.
        key_insights: List of qualitative findings or observations (2-4 insights).
        
    Returns:
        A JSON string containing the scorecard artifact payload.
    """
    artifact = {
        "artifact_type": "scorecard",
        "title": title,
        "target": target,
        "reliability": reliability,
        "stats": {
            "completed": completed_count,
            "open": open_count,
            "delayed": delayed_count,
            "abandoned": abandoned_count
        },
        "top_topics": top_topics,
        "key_insights": key_insights
    }
    return json.dumps(artifact, indent=2)

async def generate_comparison_artifact(
    title: str,
    entity_a: str,
    entity_b: str,
    joint_decisions_count: int,
    alignment_score: float,
    contrasting_viewpoints: list[str],
    key_findings: list[str]
) -> str:
    """Generate a structured side-by-side comparison JSON payload to display in the Canvas UI.
    
    Use this when the user asks to compare two leaders, analyze their alignment, contrast their positions, or check synchronization.
    
    Args:
        title: Title of the comparison (e.g. "Vinnie & Michael Alignment Analysis").
        entity_a: Name of the first leader (e.g. "Vinnie Micciche").
        entity_b: Name of the second leader (e.g. "Michael Donovan").
        joint_decisions_count: Number of joint decisions they participated in together.
        alignment_score: Alignment score percentage (joint decisions/total, e.g. 74.2).
        contrasting_viewpoints: List of bullet points detailing differences in their stances or direction changes.
        key_findings: List of summaries or strategic takeaways.
        
    Returns:
        A JSON string containing the comparison artifact payload.
    """
    artifact = {
        "artifact_type": "comparison",
        "title": title,
        "entity_a": entity_a,
        "entity_b": entity_b,
        "joint_decisions": joint_decisions_count,
        "alignment_score": alignment_score,
        "contrasting_viewpoints": contrasting_viewpoints,
        "key_findings": key_findings
    }
    return json.dumps(artifact, indent=2)

def build_agent() -> Agent:
    instruction = (
        "You are the Strolid Meeting Intelligence Assistant, a strategic chatbot "
        "designed to help teams review meeting transcripts, analyze relationship dynamics, "
        "track commitments, and generate performance scorecards.\n\n"
        "You have access to tools:\n"
        "1. `rag_search` to query semantic meeting transcripts. ALWAYS use this when asked about "
        "what people said, debates, transcript specifics, or historical context.\n"
        "2. `get_analytics_summary` to pull meeting counts, decision ratios, and reliability statistics "
        "from the data warehouse.\n"
        "3. `get_performance_report` to analyze company performance trends (revenue, marketing, operations, "
        "churn, speed-to-market) or short, mid, and long-term execution of plans (strategies, campaigns, updates, releases).\n"
        "4. `generate_presentation_artifact` to create structured presentation slide decks for the user.\n"
        "5. `generate_timeline_artifact` to create chronological event timelines.\n"
        "6. `generate_scorecard_artifact` to create structured reliability scorecards for individuals or topics.\n"
        "7. `generate_comparison_artifact` to create side-by-side comparison analyses between leaders.\n\n"
        "CRITICAL - ACTIVE FILTERS: System context parameters (such as date ranges or a list of specific meeting ID filters) "
        "will be supplied in the prompt as a '[System Context - Active Filters: ...]' prefix. "
        "You MUST apply these filters as arguments to any query tools you call (e.g. meeting_ids list, start_date, end_date) "
        "unless the user explicitly requests different filters or queries.\n\n"
        "CRITICAL - CANVAS ARTIFACTS: When you call an artifact generation tool (e.g., `generate_presentation_artifact`, "
        "`generate_timeline_artifact`, `generate_scorecard_artifact`, `generate_comparison_artifact`), "
        "do NOT write or repeat the raw JSON block in your final text response. Simply provide a helpful, natural "
        "text summary or explanation to the user. The system will automatically capture the tool's JSON output "
        "and display the interactive canvas card on the right side."
    )
    
    return Agent(
        name="meetings_agent",
        model="gemini-2.0-flash", # ADK 2.0 uses gemini-2.0-flash by default
        description="Strolid Meeting Intelligence and scoring assistant.",
        instruction=instruction,
        tools=[
            rag_search, 
            get_analytics_summary, 
            get_performance_report,
            generate_presentation_artifact, 
            generate_timeline_artifact,
            generate_scorecard_artifact,
            generate_comparison_artifact
        ],
    )
