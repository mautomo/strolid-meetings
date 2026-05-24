import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema_types import NormalizedData, PatternFlag, ExtractedMeeting, Decision, ActionItem, TopicThread, Person

NORMALIZED_DIR = Path(__file__).resolve().parents[1] / "data" / "normalized"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

def load_data() -> NormalizedData:
    all_json = NORMALIZED_DIR / "all.json"
    with open(all_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return NormalizedData(**data)

def detect_patterns(data: NormalizedData) -> list[PatternFlag]:
    flags = []

    # Zombie topics: discussed 4+ times without firm decision
    for topic in data.topics:
        if topic.mentionCount >= 4:
            firm_decisions = [
                d for d in data.decisions
                if d.topic == topic.id and d.confidence == "firm"
            ]
            if not firm_decisions:
                flags.append(PatternFlag(
                    type="zombie_topic",
                    severity="high",
                    title=f'"{topic.label}" discussed {topic.mentionCount} times without firm decision',
                    description=f"Topic has been raised in {topic.mentionCount} meetings from {topic.firstMentioned} to {topic.lastMentioned} but no firm decisions recorded.",
                    meetingRefs=topic.meetingRefs,
                    dates=[topic.firstMentioned, topic.lastMentioned],
                    relatedEntities=[topic.id]
                ))

    # Orphan actions: abandoned with no follow-up
    abandoned = [a for a in data.actionItems if a.status == "abandoned"]
    for item in abandoned:
        flags.append(PatternFlag(
            type="orphan_action",
            severity="medium",
            title=f'Abandoned: "{item.task[:60]}..."',
            description=f"Assigned to {item.owner} on {item.meetingDate}, never referenced in any later meeting.",
            meetingRefs=[item.meetingId],
            dates=[item.meetingDate],
            relatedEntities=[item.owner]
        ))

    # Recurring unresolved: same task keeps appearing
    recurring = [a for a in data.actionItems if a.status == "recurring"]
    for item in recurring:
        flags.append(PatternFlag(
            type="recurring_unresolved",
            severity="high",
            title=f'Recurring: "{item.task[:60]}..."',
            description=f"Assigned to {item.owner}, keeps reappearing across meetings without resolution.",
            meetingRefs=[item.meetingId],
            dates=[item.meetingDate],
            relatedEntities=[item.owner]
        ))

    # Direction changes (already detected in normalize)
    for change in data.directionChanges:
        severity = "high" if change.daysBetween < 30 else "medium"
        flags.append(PatternFlag(
            type="direction_change",
            severity=severity,
            title=f'Direction change on "{change.topic}" after {change.daysBetween} days',
            description=f'"{change.originalPosition[:80]}" → "{change.newPosition[:80]}"',
            meetingRefs=[change.originalMeeting, change.changeMeeting],
            dates=[change.originalDate, change.changeDate],
            relatedEntities=[change.topic]
        ))

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(flags, key=lambda f: severity_order[f.severity])

def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def render_timeline(meetings: list[ExtractedMeeting]) -> str:
    type_colors = {
        "leadership": "#6366f1",
        "marketing": "#ec4899",
        "product": "#10b981",
        "one-on-one": "#f59e0b",
        "standup": "#8b5cf6",
        "strategy": "#3b82f6",
        "other": "#6b7280"
    }

    items = []
    for m in meetings:
        color = type_colors.get(m.type, "#6b7280")
        decisions_html = ""
        if m.decisions:
            list_items = "".join(
                f'<li><span class="confidence-{d.confidence}">[{d.confidence}]</span> {escape_html(d.description)}</li>'
                for d in m.decisions
            )
            decisions_html = f'<div class="timeline-decisions"><strong>Decisions:</strong><ul>{list_items}</ul></div>'
            
        items.append(f"""
        <div class="timeline-item" style="border-left-color: {color}">
          <div class="timeline-date">{m.date}</div>
          <div class="timeline-title">{escape_html(m.title)}</div>
          <div class="timeline-meta">
            <span class="badge" style="background: {color}">{m.type}</span>
            <span class="attendee-count">{len(m.attendees)} attendees</span>
            <span class="decision-count">{len(m.decisions)} decisions</span>
            <span class="action-count">{len(m.actionItems)} actions</span>
          </div>
          <div class="timeline-summary">{escape_html(m.summary)}</div>
          {decisions_html}
        </div>""")
        
    legend_items = "".join(
        f'<span class="legend-item"><span class="legend-dot" style="background:{color}"></span>{type_name}</span>'
        for type_name, color in type_colors.items()
    )

    return f"""<section id="timeline"><h2>Chronological Timeline</h2>
    <div class="legend">{legend_items}</div>
    <div class="timeline">{"".join(items)}</div></section>"""

def render_people_matrix(people: list[Person], meetings: list[ExtractedMeeting]) -> str:
    series_list = sorted(list(set(m.series for m in meetings)))
    series_map = {s: (s[:22] + "..." if len(s) > 25 else s) for s in series_list}

    # Group meetings by series
    meetings_by_series = {}
    for m in meetings:
        meetings_by_series.setdefault(m.series, []).append(m)

    # Only show series with 2+ meetings
    frequent_series = [s for s in series_list if len(meetings_by_series.get(s, [])) >= 2]

    header_cells = "".join(
        f'<th title="{escape_html(s)}">{escape_html(series_map.get(s, s))}</th>'
        for s in frequent_series
    )

    rows = []
    for p in people[:15]: # Top 15 people
        cells = []
        for s in frequent_series:
            series_meetings = meetings_by_series.get(s, [])
            # Count attendance
            count = sum(1 for m in series_meetings if any(p.name.lower().split()[0] in a.lower() for a in m.attendees))
            intensity = min(count / (len(series_meetings) or 1), 1.0)
            bg = f"rgba(99, 102, 241, {0.15 + intensity * 0.7})" if count > 0 else "transparent"
            cells.append(f'<td style="background:{bg};text-align:center" title="{count}/{len(series_meetings)}">{count or ""}</td>')
            
        rows.append(f"""<tr>
            <td class="person-name"><strong>{escape_html(p.name)}</strong><br><small>{p.department or ""} | {p.meetingCount} meetings</small></td>
            {"".join(cells)}
        </tr>""")

    return f"""<section id="people"><h2>People &times; Meeting Series Matrix</h2>
    <div class="table-wrap"><table class="matrix"><thead><tr><th>Person</th>{header_cells}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>"""

def render_decision_log(decisions: list[Decision]) -> str:
    by_topic = {}
    for d in decisions:
        by_topic.setdefault(d.topic, []).append(d)

    sorted_topics = sorted(by_topic.items(), key=lambda x: len(x[1]), reverse=True)[:30]

    sections = []
    for topic, decs in sorted_topics:
        nodes = []
        decs.sort(key=lambda x: x.meetingDate)
        
        for d in decs:
            cls = "superseded" if d.supersededBy else "current"
            overridden = '<span class="overridden">SUPERSEDED</span>' if d.supersededBy else ""
            chain_arrow = '<div class="chain-arrow">&#x2193; changed to</div>' if d.supersededBy else ""
            
            nodes.append(f"""
            <div class="decision-node {cls}">
              <div class="decision-date">{d.meetingDate}</div>
              <div class="decision-text">{escape_html(d.description)}</div>
              <div class="decision-meta">
                <span class="confidence-{d.confidence}">{d.confidence}</span>
                by {", ".join(escape_html(name) for name in d.decidedBy)}
                {overridden}
              </div>
            </div>
            {chain_arrow}""")

        sections.append(f"""
        <div class="decision-topic">
          <h3>{escape_html(topic)} <span class="count">({len(decs)} decisions)</span></h3>
          <div class="decision-chain">{"".join(nodes)}</div>
        </div>""")

    return f"""<section id="decisions"><h2>Decision Log with Lineage</h2>{"".join(sections)}</section>"""

def render_action_scorecard(actions: list[ActionItem]) -> str:
    total = len(actions)
    done = sum(1 for a in actions if a.status == "done")
    open_count = sum(1 for a in actions if a.status == "open")
    abandoned = sum(1 for a in actions if a.status == "abandoned")
    recurring = sum(1 for a in actions if a.status == "recurring")
    rate = round((done / total) * 100) if total > 0 else 0

    # By owner
    by_owner = {}
    for a in actions:
        by_owner.setdefault(a.owner, {"total": 0, "done": 0, "abandoned": 0})
        stats = by_owner[a.owner]
        stats["total"] += 1
        if a.status == "done":
            stats["done"] += 1
        elif a.status == "abandoned":
            stats["abandoned"] += 1

    owner_rows = []
    for name, stats in sorted(by_owner.items(), key=lambda x: x[1]["total"], reverse=True)[:15]:
        rate_o = round((stats["done"] / stats["total"]) * 100) if stats["total"] > 0 else 0
        owner_rows.append(f"""
        <tr>
          <td>{escape_html(name)}</td>
          <td>{stats["total"]}</td>
          <td>{stats["done"]}</td>
          <td>{stats["abandoned"]}</td>
          <td>{rate_o}%</td>
        </tr>""")

    return f"""<section id="actions"><h2>Action Item Scorecard</h2>
    <div class="scorecard-grid">
      <div class="score-card"><div class="score-number">{total}</div><div class="score-label">Total</div></div>
      <div class="score-card done"><div class="score-number">{done}</div><div class="score-label">Completed</div></div>
      <div class="score-card open"><div class="score-number">{open_count}</div><div class="score-label">Open</div></div>
      <div class="score-card abandoned"><div class="score-number">{abandoned}</div><div class="score-label">Abandoned</div></div>
      <div class="score-card recurring"><div class="score-number">{recurring}</div><div class="score-label">Recurring</div></div>
      <div class="score-card rate"><div class="score-number">{rate}%</div><div class="score-label">Completion Rate</div></div>
    </div>
    <h3>By Owner</h3>
    <div class="table-wrap"><table><thead><tr><th>Owner</th><th>Total</th><th>Done</th><th>Abandoned</th><th>Rate</th></tr></thead><tbody>{"".join(owner_rows)}</tbody></table></div></section>"""

def render_topic_frequency(topics: list[TopicThread]) -> str:
    top20 = topics[:20]
    max_count = max(t.mentionCount for t in top20) if top20 else 1

    bars = []
    for t in top20:
        pct = (t.mentionCount / max_count) * 100
        bars.append(f"""
        <div class="topic-bar">
          <div class="topic-label">{escape_html(t.label)}</div>
          <div class="topic-bar-track">
            <div class="topic-bar-fill" style="width: {pct}%">
              {t.mentionCount}
            </div>
          </div>
          <div class="topic-dates">{t.firstMentioned} → {t.lastMentioned}</div>
        </div>""")

    return f"""<section id="topics"><h2>Topic Frequency</h2>
    <div class="topic-chart">{"".join(bars)}</div></section>"""

def render_pattern_flags(flags: list[PatternFlag]) -> str:
    if not flags:
        return '<section id="patterns"><h2>Pattern Flags</h2><p>No patterns detected.</p></section>'

    sev_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#6b7280"}
    type_icons = {
        "inconsistency": "&#x26A0;",
        "direction_change": "&#x21C4;",
        "zombie_topic": "&#x1F6A8;",
        "orphan_action": "&#x274C;",
        "echo_chamber": "&#x1F50A;",
        "recurring_unresolved": "&#x1F504;"
    }

    items = []
    for f in flags:
        color = sev_colors.get(f.severity, "#6b7280")
        icon = type_icons.get(f.type, "?")
        items.append(f"""
        <div class="flag-item" style="border-left-color: {color}">
          <div class="flag-header">
            <span class="flag-icon">{icon}</span>
            <span class="flag-severity" style="color: {color}">{f.severity.upper()}</span>
            <span class="flag-type">{f.type.replace('_', ' ')}</span>
          </div>
          <div class="flag-title">{escape_html(f.title)}</div>
          <div class="flag-desc">{escape_html(f.description)}</div>
          <div class="flag-refs">{" → ".join(f.dates)}</div>
        </div>""")

    by_sev = {"high": 0, "medium": 0, "low": 0}
    for f in flags:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    return f"""<section id="patterns"><h2>Pattern Flags</h2>
    <div class="flag-summary">
      <span style="color:{sev_colors['high']}">{by_sev['high']} High</span> |
      <span style="color:{sev_colors['medium']}">{by_sev['medium']} Medium</span> |
      <span style="color:{sev_colors['low']}">{by_sev['low']} Low</span> |
      <strong>{len(flags)} Total</strong>
    </div>
    <div class="flag-list">{"".join(items)}</div></section>"""

def generate_html(data: NormalizedData, flags: list[PatternFlag]) -> str:
    date_range = f"{data.meetings[0].date} to {data.meetings[-1].date}" if data.meetings else "N/A"
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Read the CSS styling and baseline template structure from report.ts 
    # and embed it here dynamically
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Strolid Meeting Intelligence - Python Backend Baseline</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text-muted: #94a3b8; --accent: #6366f1;
    --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
  h1 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.5rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--surface2); }}
  h3 {{ font-size: 1.1rem; margin: 1rem 0 0.5rem; color: var(--text-muted); }}

  nav {{ position: sticky; top: 0; background: var(--bg); padding: 1rem 0; z-index: 100; border-bottom: 1px solid var(--surface2); margin-bottom: 1rem; }}
  nav a {{ color: var(--accent); text-decoration: none; margin-right: 1.5rem; font-size: 0.9rem; }}
  nav a:hover {{ text-decoration: underline; }}

  /* Timeline */
  .timeline-item {{ background: var(--surface); border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1rem; border-left: 4px solid var(--accent); }}
  .timeline-date {{ font-size: 0.85rem; color: var(--accent); font-weight: 600; }}
  .timeline-title {{ font-size: 1.1rem; font-weight: 600; margin: 0.25rem 0; }}
  .timeline-meta {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 0.5rem 0; font-size: 0.8rem; }}
  .timeline-summary {{ font-size: 0.9rem; color: var(--text-muted); margin-top: 0.5rem; }}
  .timeline-decisions {{ margin-top: 0.75rem; font-size: 0.85rem; }}
  .timeline-decisions ul {{ margin-left: 1.2rem; margin-top: 0.25rem; }}
  .timeline-decisions li {{ margin-bottom: 0.25rem; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; color: white; font-size: 0.75rem; font-weight: 600; }}
  .legend {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; font-size: 0.85rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4rem; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}

  .confidence-firm {{ color: var(--green); font-weight: 600; }}
  .confidence-tentative {{ color: var(--yellow); }}
  .confidence-exploratory {{ color: var(--text-muted); font-style: italic; }}

  /* Tables */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid var(--surface2); font-size: 0.85rem; }}
  th {{ background: var(--surface2); font-weight: 600; font-size: 0.8rem; white-space: nowrap; }}
  .person-name {{ min-width: 160px; }}

  /* Scorecard */
  .scorecard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
  .score-card {{ background: var(--surface); border-radius: 8px; padding: 1.25rem; text-align: center; }}
  .score-number {{ font-size: 2rem; font-weight: 700; }}
  .score-label {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }}
  .score-card.done .score-number {{ color: var(--green); }}
  .score-card.open .score-number {{ color: var(--blue); }}
  .score-card.abandoned .score-number {{ color: var(--red); }}
  .score-card.recurring .score-number {{ color: var(--yellow); }}
  .score-card.rate .score-number {{ color: var(--accent); }}

  /* Topic bars */
  .topic-chart {{ display: flex; flex-direction: column; gap: 0.5rem; }}
  .topic-bar {{ display: grid; grid-template-columns: 200px 1fr 180px; gap: 0.75rem; align-items: center; font-size: 0.85rem; }}
  .topic-label {{ text-align: right; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .topic-bar-track {{ background: var(--surface); border-radius: 4px; height: 28px; overflow: hidden; }}
  .topic-bar-fill {{ background: var(--accent); height: 100%; display: flex; align-items: center; padding: 0 0.5rem; font-size: 0.75rem; font-weight: 600; min-width: 30px; border-radius: 4px; }}
  .topic-dates {{ font-size: 0.75rem; color: var(--text-muted); }}

  /* Decision log */
  .decision-topic {{ background: var(--surface); border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }}
  .decision-topic h3 {{ color: var(--text); margin: 0 0 0.75rem; }}
  .count {{ color: var(--text-muted); font-weight: normal; font-size: 0.9rem; }}
  .decision-node {{ padding: 0.75rem; border-radius: 6px; background: var(--surface2); margin-bottom: 0.5rem; }}
  .decision-node.superseded {{ opacity: 0.6; }}
  .decision-date {{ font-size: 0.8rem; color: var(--accent); font-weight: 600; }}
  .decision-text {{ margin: 0.25rem 0; }}
  .decision-meta {{ font-size: 0.8rem; color: var(--text-muted); }}
  .overridden {{ color: var(--red); font-weight: 600; margin-left: 0.5rem; }}
  .chain-arrow {{ text-align: center; color: var(--yellow); font-weight: 600; margin: 0.25rem 0; }}

  /* Pattern flags */
  .flag-summary {{ font-size: 1rem; margin-bottom: 1rem; padding: 0.75rem; background: var(--surface); border-radius: 6px; }}
  .flag-list {{ display: flex; flex-direction: column; gap: 0.75rem; }}
  .flag-item {{ background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem; border-left: 4px solid var(--text-muted); }}
  .flag-header {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-size: 0.85rem; }}
  .flag-icon {{ font-size: 1.1rem; }}
  .flag-severity {{ font-weight: 700; font-size: 0.75rem; }}
  .flag-type {{ color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; }}
  .flag-title {{ font-weight: 600; margin-bottom: 0.25rem; }}
  .flag-desc {{ font-size: 0.9rem; color: var(--text-muted); }}
  .flag-refs {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.4rem; }}

  @media (max-width: 768px) {{
    .topic-bar {{ grid-template-columns: 1fr; }}
    .topic-label {{ text-align: left; }}
    .header-stats {{ gap: 1rem; }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1>Strolid Meeting Intelligence</h1>
  <p style="color:var(--text-muted)">Phase 1 Python Backend Baseline | {date_range} | Generated {current_date}</p>

  <div class="header-stats" style="display:flex;gap:2rem;margin:1rem 0 2rem;flex-wrap:wrap;">
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(data.meetings)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">Meetings</div></div>
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(data.people)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">People</div></div>
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(data.decisions)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">Decisions</div></div>
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(data.actionItems)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">Action Items</div></div>
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(data.topics)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">Topics</div></div>
    <div class="header-stat" style="background:var(--surface);padding:1rem 1.5rem;border-radius:8px;"><div class="num" style="font-size:1.8rem;font-weight:700;color:var(--accent);">{len(flags)}</div><div class="lbl" style="font-size:0.85rem;color:var(--text-muted);">Flags</div></div>
  </div>

  <nav>
    <a href="#timeline">Timeline</a>
    <a href="#people">People</a>
    <a href="#decisions">Decisions</a>
    <a href="#actions">Actions</a>
    <a href="#topics">Topics</a>
    <a href="#patterns">Patterns</a>
  </nav>

  {render_timeline(data.meetings)}
  {render_people_matrix(data.people, data.meetings)}
  {render_decision_log(data.decisions)}
  {render_action_scorecard(data.actionItems)}
  {render_topic_frequency(data.topics)}
  {render_pattern_flags(flags)}

  <footer style="margin-top:3rem;padding:2rem 0;border-top:1px solid var(--surface2);color:var(--text-muted);font-size:0.85rem;">
    <p>Meeting Intelligence Pipeline v1.0 | Python Backend Baseline</p>
    <p>{len(data.meetings)} meetings analyzed | {len(data.decisions)} decisions tracked | {len(data.actionItems)} action items monitored</p>
  </footer>
</div>
</body>
</html>"""

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading normalized data...")
    data = load_data()
    print(f"  {len(data.meetings)} meetings, {len(data.people)} people, {len(data.decisions)} decisions\n")

    print("Detecting patterns...")
    flags = detect_patterns(data)
    print(f"  Found {len(flags)} pattern flags\n")

    print("Generating HTML report...")
    html = generate_html(data, flags)

    output_path = OUTPUT_DIR / "baseline-report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport generated: {output_path}")

    # Write pattern flags to JSON
    flags_path = OUTPUT_DIR / "pattern-flags.json"
    with open(flags_path, "w", encoding="utf-8") as f:
        json.dump([f.model_dump() for f in flags], f, indent=2)
    print(f"Pattern flags saved to: {flags_path}")

if __name__ == "__main__":
    main()
