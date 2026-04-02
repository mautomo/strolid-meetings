import * as fs from "node:fs";
import * as path from "node:path";
import type {
  ActionItem,
  Decision,
  DirectionChange,
  ExtractedMeeting,
  NormalizedData,
  PatternFlag,
  Person,
  TopicThread,
} from "./types.js";

const NORMALIZED_DIR = path.resolve(import.meta.dirname, "../data/normalized");
const OUTPUT_DIR = path.resolve(import.meta.dirname, "../output");

function loadData(): NormalizedData {
  return JSON.parse(
    fs.readFileSync(path.join(NORMALIZED_DIR, "all.json"), "utf-8"),
  ) as NormalizedData;
}

function detectPatterns(data: NormalizedData): PatternFlag[] {
  const flags: PatternFlag[] = [];

  // Zombie topics: discussed 4+ times without firm decision
  for (const topic of data.topics) {
    if (topic.mentionCount >= 4) {
      const firmDecisions = data.decisions.filter(
        (d) => d.topic === topic.id && d.confidence === "firm",
      );
      if (firmDecisions.length === 0) {
        flags.push({
          type: "zombie_topic",
          severity: "high",
          title: `"${topic.label}" discussed ${topic.mentionCount} times without firm decision`,
          description: `Topic has been raised in ${topic.mentionCount} meetings from ${topic.firstMentioned} to ${topic.lastMentioned} but no firm decisions recorded.`,
          meetingRefs: topic.meetingRefs,
          dates: [topic.firstMentioned, topic.lastMentioned],
          relatedEntities: [topic.id],
        });
      }
    }
  }

  // Orphan actions: abandoned with no follow-up
  const abandoned = data.actionItems.filter((a) => a.status === "abandoned");
  for (const item of abandoned) {
    flags.push({
      type: "orphan_action",
      severity: "medium",
      title: `Abandoned: "${item.task.slice(0, 60)}..."`,
      description: `Assigned to ${item.owner} on ${item.meetingDate}, never referenced in any later meeting.`,
      meetingRefs: [item.meetingId],
      dates: [item.meetingDate],
      relatedEntities: [item.owner],
    });
  }

  // Recurring unresolved: same task keeps appearing
  const recurring = data.actionItems.filter((a) => a.status === "recurring");
  for (const item of recurring) {
    flags.push({
      type: "recurring_unresolved",
      severity: "high",
      title: `Recurring: "${item.task.slice(0, 60)}..."`,
      description: `Assigned to ${item.owner}, keeps reappearing across meetings without resolution.`,
      meetingRefs: [item.meetingId],
      dates: [item.meetingDate],
      relatedEntities: [item.owner],
    });
  }

  // Direction changes (already detected in normalize)
  for (const change of data.directionChanges) {
    flags.push({
      type: "direction_change",
      severity: change.daysBetween < 30 ? "high" : "medium",
      title: `Direction change on "${change.topic}" after ${change.daysBetween} days`,
      description: `"${change.originalPosition.slice(0, 80)}" → "${change.newPosition.slice(0, 80)}"`,
      meetingRefs: [change.originalMeeting, change.changeMeeting],
      dates: [change.originalDate, change.changeDate],
      relatedEntities: [change.topic],
    });
  }

  return flags.sort((a, b) => {
    const sevOrder = { high: 0, medium: 1, low: 2 };
    return sevOrder[a.severity] - sevOrder[b.severity];
  });
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderTimeline(meetings: ExtractedMeeting[]): string {
  const typeColors: Record<string, string> = {
    leadership: "#6366f1",
    marketing: "#ec4899",
    product: "#10b981",
    "one-on-one": "#f59e0b",
    standup: "#8b5cf6",
    strategy: "#3b82f6",
    other: "#6b7280",
  };

  const items = meetings
    .map(
      (m) => `
    <div class="timeline-item" style="border-left-color: ${typeColors[m.type] || "#6b7280"}">
      <div class="timeline-date">${m.date}</div>
      <div class="timeline-title">${escapeHtml(m.title)}</div>
      <div class="timeline-meta">
        <span class="badge" style="background: ${typeColors[m.type] || "#6b7280"}">${m.type}</span>
        <span class="attendee-count">${m.attendees.length} attendees</span>
        <span class="decision-count">${m.decisions.length} decisions</span>
        <span class="action-count">${m.actionItems.length} actions</span>
      </div>
      <div class="timeline-summary">${escapeHtml(m.summary)}</div>
      ${
        m.decisions.length > 0
          ? `<div class="timeline-decisions">
        <strong>Decisions:</strong>
        <ul>${m.decisions.map((d) => `<li><span class="confidence-${d.confidence}">[${d.confidence}]</span> ${escapeHtml(d.description)}</li>`).join("")}</ul>
      </div>`
          : ""
      }
    </div>`,
    )
    .join("\n");

  return `<section id="timeline"><h2>Chronological Timeline</h2>
    <div class="legend">${Object.entries(typeColors)
      .map(
        ([type, color]) =>
          `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${type}</span>`,
      )
      .join("")}</div>
    <div class="timeline">${items}</div></section>`;
}

function renderPeopleMatrix(
  people: Person[],
  meetings: ExtractedMeeting[],
): string {
  const series = [...new Set(meetings.map((m) => m.series))].sort();
  const seriesMap = new Map<string, string>();
  for (const s of series) {
    const short = s.length > 25 ? s.slice(0, 22) + "..." : s;
    seriesMap.set(s, short);
  }

  // Group meetings by series
  const meetingsBySeries = new Map<string, ExtractedMeeting[]>();
  for (const m of meetings) {
    if (!meetingsBySeries.has(m.series)) meetingsBySeries.set(m.series, []);
    meetingsBySeries.get(m.series)!.push(m);
  }

  // Only show series with 2+ meetings
  const frequentSeries = series.filter(
    (s) => (meetingsBySeries.get(s)?.length || 0) >= 2,
  );

  const headerCells = frequentSeries
    .map(
      (s) =>
        `<th title="${escapeHtml(s)}">${escapeHtml(seriesMap.get(s) || s)}</th>`,
    )
    .join("");

  const rows = people
    .slice(0, 15) // Top 15 people
    .map((p) => {
      const cells = frequentSeries
        .map((s) => {
          const seriesMeetings = meetingsBySeries.get(s) || [];
          const count = seriesMeetings.filter((m) =>
            m.attendees.some((a) =>
              a.toLowerCase().includes(p.name.toLowerCase().split(" ")[0]),
            ),
          ).length;
          const intensity = Math.min(count / (seriesMeetings.length || 1), 1);
          const bg =
            count > 0
              ? `rgba(99, 102, 241, ${0.15 + intensity * 0.7})`
              : "transparent";
          return `<td style="background:${bg};text-align:center" title="${count}/${seriesMeetings.length}">${count || ""}</td>`;
        })
        .join("");
      return `<tr><td class="person-name"><strong>${escapeHtml(p.name)}</strong><br><small>${p.department || ""} | ${p.meetingCount} meetings</small></td>${cells}</tr>`;
    })
    .join("\n");

  return `<section id="people"><h2>People &times; Meeting Series Matrix</h2>
    <div class="table-wrap"><table class="matrix"><thead><tr><th>Person</th>${headerCells}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function renderDecisionLog(decisions: Decision[]): string {
  const byTopic = new Map<string, Decision[]>();
  for (const d of decisions) {
    if (!byTopic.has(d.topic)) byTopic.set(d.topic, []);
    byTopic.get(d.topic)!.push(d);
  }

  const topics = [...byTopic.entries()]
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 30);

  const sections = topics
    .map(
      ([topic, decs]) => `
    <div class="decision-topic">
      <h3>${escapeHtml(topic)} <span class="count">(${decs.length} decisions)</span></h3>
      <div class="decision-chain">
        ${decs
          .sort(
            (a, b) =>
              new Date(a.meetingDate).getTime() -
              new Date(b.meetingDate).getTime(),
          )
          .map(
            (d) => `
          <div class="decision-node ${d.supersededBy ? "superseded" : "current"}">
            <div class="decision-date">${d.meetingDate}</div>
            <div class="decision-text">${escapeHtml(d.description)}</div>
            <div class="decision-meta">
              <span class="confidence-${d.confidence}">${d.confidence}</span>
              by ${d.decidedBy.map(escapeHtml).join(", ")}
              ${d.supersededBy ? '<span class="overridden">SUPERSEDED</span>' : ""}
            </div>
          </div>
          ${d.supersededBy ? '<div class="chain-arrow">&#x2193; changed to</div>' : ""}`,
          )
          .join("")}
      </div>
    </div>`,
    )
    .join("\n");

  return `<section id="decisions"><h2>Decision Log with Lineage</h2>${sections}</section>`;
}

function renderActionScorecard(actions: ActionItem[]): string {
  const total = actions.length;
  const done = actions.filter((a) => a.status === "done").length;
  const open = actions.filter((a) => a.status === "open").length;
  const abandoned = actions.filter((a) => a.status === "abandoned").length;
  const recurring = actions.filter((a) => a.status === "recurring").length;
  const completionRate = total > 0 ? Math.round((done / total) * 100) : 0;

  // By owner
  const byOwner = new Map<
    string,
    { total: number; done: number; abandoned: number }
  >();
  for (const a of actions) {
    if (!byOwner.has(a.owner))
      byOwner.set(a.owner, { total: 0, done: 0, abandoned: 0 });
    const o = byOwner.get(a.owner)!;
    o.total++;
    if (a.status === "done") o.done++;
    if (a.status === "abandoned") o.abandoned++;
  }

  const ownerRows = [...byOwner.entries()]
    .sort((a, b) => b[1].total - a[1].total)
    .slice(0, 15)
    .map(
      ([name, stats]) => `
    <tr>
      <td>${escapeHtml(name)}</td>
      <td>${stats.total}</td>
      <td>${stats.done}</td>
      <td>${stats.abandoned}</td>
      <td>${stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0}%</td>
    </tr>`,
    )
    .join("");

  return `<section id="actions"><h2>Action Item Scorecard</h2>
    <div class="scorecard-grid">
      <div class="score-card"><div class="score-number">${total}</div><div class="score-label">Total</div></div>
      <div class="score-card done"><div class="score-number">${done}</div><div class="score-label">Completed</div></div>
      <div class="score-card open"><div class="score-number">${open}</div><div class="score-label">Open</div></div>
      <div class="score-card abandoned"><div class="score-number">${abandoned}</div><div class="score-label">Abandoned</div></div>
      <div class="score-card recurring"><div class="score-number">${recurring}</div><div class="score-label">Recurring</div></div>
      <div class="score-card rate"><div class="score-number">${completionRate}%</div><div class="score-label">Completion Rate</div></div>
    </div>
    <h3>By Owner</h3>
    <div class="table-wrap"><table><thead><tr><th>Owner</th><th>Total</th><th>Done</th><th>Abandoned</th><th>Rate</th></tr></thead><tbody>${ownerRows}</tbody></table></div></section>`;
}

function renderTopicFrequency(topics: TopicThread[]): string {
  const top20 = topics.slice(0, 20);
  const maxCount = Math.max(...top20.map((t) => t.mentionCount));

  const bars = top20
    .map(
      (t) => `
    <div class="topic-bar">
      <div class="topic-label">${escapeHtml(t.label)}</div>
      <div class="topic-bar-track">
        <div class="topic-bar-fill" style="width: ${(t.mentionCount / maxCount) * 100}%">
          ${t.mentionCount}
        </div>
      </div>
      <div class="topic-dates">${t.firstMentioned} → ${t.lastMentioned}</div>
    </div>`,
    )
    .join("\n");

  return `<section id="topics"><h2>Topic Frequency</h2>
    <div class="topic-chart">${bars}</div></section>`;
}

function renderPatternFlags(flags: PatternFlag[]): string {
  if (flags.length === 0)
    return `<section id="patterns"><h2>Pattern Flags</h2><p>No patterns detected.</p></section>`;

  const sevColors = { high: "#ef4444", medium: "#f59e0b", low: "#6b7280" };
  const typeIcons = {
    inconsistency: "&#x26A0;",
    direction_change: "&#x21C4;",
    zombie_topic: "&#x1F6A8;",
    orphan_action: "&#x274C;",
    echo_chamber: "&#x1F50A;",
    recurring_unresolved: "&#x1F504;",
  };

  const items = flags
    .map(
      (f) => `
    <div class="flag-item" style="border-left-color: ${sevColors[f.severity]}">
      <div class="flag-header">
        <span class="flag-icon">${typeIcons[f.type] || "?"}</span>
        <span class="flag-severity" style="color: ${sevColors[f.severity]}">${f.severity.toUpperCase()}</span>
        <span class="flag-type">${f.type.replace(/_/g, " ")}</span>
      </div>
      <div class="flag-title">${escapeHtml(f.title)}</div>
      <div class="flag-desc">${escapeHtml(f.description)}</div>
      <div class="flag-refs">${f.dates.join(" → ")}</div>
    </div>`,
    )
    .join("\n");

  const bySeverity = { high: 0, medium: 0, low: 0 };
  for (const f of flags) bySeverity[f.severity]++;

  return `<section id="patterns"><h2>Pattern Flags</h2>
    <div class="flag-summary">
      <span style="color:${sevColors.high}">${bySeverity.high} High</span> |
      <span style="color:${sevColors.medium}">${bySeverity.medium} Medium</span> |
      <span style="color:${sevColors.low}">${bySeverity.low} Low</span> |
      <strong>${flags.length} Total</strong>
    </div>
    <div class="flag-list">${items}</div></section>`;
}

function generateHtml(data: NormalizedData, flags: PatternFlag[]): string {
  const meetingDateRange =
    data.meetings.length > 0
      ? `${data.meetings[0].date} to ${data.meetings[data.meetings.length - 1].date}`
      : "N/A";

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Strolid Meeting Intelligence - Phase 1 Baseline</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text-muted: #94a3b8; --accent: #6366f1;
    --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
  h1 { font-size: 2rem; margin-bottom: 0.5rem; }
  h2 { font-size: 1.5rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--surface2); }
  h3 { font-size: 1.1rem; margin: 1rem 0 0.5rem; color: var(--text-muted); }

  /* Header stats */
  .header-stats { display: flex; gap: 2rem; margin: 1rem 0 2rem; flex-wrap: wrap; }
  .header-stat { background: var(--surface); padding: 1rem 1.5rem; border-radius: 8px; }
  .header-stat .num { font-size: 1.8rem; font-weight: 700; color: var(--accent); }
  .header-stat .lbl { font-size: 0.85rem; color: var(--text-muted); }

  /* Nav */
  nav { position: sticky; top: 0; background: var(--bg); padding: 1rem 0; z-index: 100; border-bottom: 1px solid var(--surface2); margin-bottom: 1rem; }
  nav a { color: var(--accent); text-decoration: none; margin-right: 1.5rem; font-size: 0.9rem; }
  nav a:hover { text-decoration: underline; }

  /* Timeline */
  .timeline { position: relative; }
  .timeline-item { background: var(--surface); border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1rem; border-left: 4px solid var(--accent); }
  .timeline-date { font-size: 0.85rem; color: var(--accent); font-weight: 600; }
  .timeline-title { font-size: 1.1rem; font-weight: 600; margin: 0.25rem 0; }
  .timeline-meta { display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 0.5rem 0; font-size: 0.8rem; }
  .timeline-summary { font-size: 0.9rem; color: var(--text-muted); margin-top: 0.5rem; }
  .timeline-decisions { margin-top: 0.75rem; font-size: 0.85rem; }
  .timeline-decisions ul { margin-left: 1.2rem; margin-top: 0.25rem; }
  .timeline-decisions li { margin-bottom: 0.25rem; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; color: white; font-size: 0.75rem; font-weight: 600; }
  .legend { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; font-size: 0.85rem; }
  .legend-item { display: flex; align-items: center; gap: 0.4rem; }
  .legend-dot { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }

  /* Confidence badges */
  .confidence-firm { color: var(--green); font-weight: 600; }
  .confidence-tentative { color: var(--yellow); }
  .confidence-exploratory { color: var(--text-muted); font-style: italic; }

  /* Tables */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 8px; overflow: hidden; }
  th, td { padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid var(--surface2); font-size: 0.85rem; }
  th { background: var(--surface2); font-weight: 600; font-size: 0.8rem; white-space: nowrap; }
  .person-name { min-width: 160px; }

  /* Scorecard */
  .scorecard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .score-card { background: var(--surface); border-radius: 8px; padding: 1.25rem; text-align: center; }
  .score-number { font-size: 2rem; font-weight: 700; }
  .score-label { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }
  .score-card.done .score-number { color: var(--green); }
  .score-card.open .score-number { color: var(--blue); }
  .score-card.abandoned .score-number { color: var(--red); }
  .score-card.recurring .score-number { color: var(--yellow); }
  .score-card.rate .score-number { color: var(--accent); }

  /* Topic bars */
  .topic-chart { display: flex; flex-direction: column; gap: 0.5rem; }
  .topic-bar { display: grid; grid-template-columns: 200px 1fr 180px; gap: 0.75rem; align-items: center; font-size: 0.85rem; }
  .topic-label { text-align: right; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .topic-bar-track { background: var(--surface); border-radius: 4px; height: 28px; overflow: hidden; }
  .topic-bar-fill { background: var(--accent); height: 100%; display: flex; align-items: center; padding: 0 0.5rem; font-size: 0.75rem; font-weight: 600; min-width: 30px; border-radius: 4px; }
  .topic-dates { font-size: 0.75rem; color: var(--text-muted); }

  /* Decision log */
  .decision-topic { background: var(--surface); border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }
  .decision-topic h3 { color: var(--text); margin: 0 0 0.75rem; }
  .count { color: var(--text-muted); font-weight: normal; font-size: 0.9rem; }
  .decision-node { padding: 0.75rem; border-radius: 6px; background: var(--surface2); margin-bottom: 0.5rem; }
  .decision-node.superseded { opacity: 0.6; }
  .decision-date { font-size: 0.8rem; color: var(--accent); font-weight: 600; }
  .decision-text { margin: 0.25rem 0; }
  .decision-meta { font-size: 0.8rem; color: var(--text-muted); }
  .overridden { color: var(--red); font-weight: 600; margin-left: 0.5rem; }
  .chain-arrow { text-align: center; color: var(--yellow); font-weight: 600; margin: 0.25rem 0; }

  /* Pattern flags */
  .flag-summary { font-size: 1rem; margin-bottom: 1rem; padding: 0.75rem; background: var(--surface); border-radius: 6px; }
  .flag-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .flag-item { background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem; border-left: 4px solid var(--text-muted); }
  .flag-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; font-size: 0.85rem; }
  .flag-icon { font-size: 1.1rem; }
  .flag-severity { font-weight: 700; font-size: 0.75rem; }
  .flag-type { color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; }
  .flag-title { font-weight: 600; margin-bottom: 0.25rem; }
  .flag-desc { font-size: 0.9rem; color: var(--text-muted); }
  .flag-refs { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.4rem; }

  @media (max-width: 768px) {
    .topic-bar { grid-template-columns: 1fr; }
    .topic-label { text-align: left; }
    .header-stats { gap: 1rem; }
  }
</style>
</head>
<body>
<div class="container">
  <h1>Strolid Meeting Intelligence</h1>
  <p style="color:var(--text-muted)">Phase 1 Baseline Report | ${meetingDateRange} | Generated ${new Date().toISOString().split("T")[0]}</p>

  <div class="header-stats">
    <div class="header-stat"><div class="num">${data.meetings.length}</div><div class="lbl">Meetings</div></div>
    <div class="header-stat"><div class="num">${data.people.length}</div><div class="lbl">People</div></div>
    <div class="header-stat"><div class="num">${data.decisions.length}</div><div class="lbl">Decisions</div></div>
    <div class="header-stat"><div class="num">${data.actionItems.length}</div><div class="lbl">Action Items</div></div>
    <div class="header-stat"><div class="num">${data.topics.length}</div><div class="lbl">Topics</div></div>
    <div class="header-stat"><div class="num">${flags.length}</div><div class="lbl">Flags</div></div>
  </div>

  <nav>
    <a href="#timeline">Timeline</a>
    <a href="#people">People</a>
    <a href="#decisions">Decisions</a>
    <a href="#actions">Actions</a>
    <a href="#topics">Topics</a>
    <a href="#patterns">Patterns</a>
  </nav>

  ${renderTimeline(data.meetings)}
  ${renderPeopleMatrix(data.people, data.meetings)}
  ${renderDecisionLog(data.decisions)}
  ${renderActionScorecard(data.actionItems)}
  ${renderTopicFrequency(data.topics)}
  ${renderPatternFlags(flags)}

  <footer style="margin-top:3rem;padding:2rem 0;border-top:1px solid var(--surface2);color:var(--text-muted);font-size:0.85rem;">
    <p>Meeting Intelligence Pipeline v1.0 | Phase 1 Baseline</p>
    <p>${data.meetings.length} meetings analyzed | ${data.decisions.length} decisions tracked | ${data.actionItems.length} action items monitored</p>
  </footer>
</div>
</body>
</html>`;
}

function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log("Loading normalized data...");
  const data = loadData();
  console.log(
    `  ${data.meetings.length} meetings, ${data.people.length} people, ${data.decisions.length} decisions\n`,
  );

  console.log("Detecting patterns...");
  const flags = detectPatterns(data);
  console.log(`  Found ${flags.length} pattern flags\n`);

  console.log("Generating HTML report...");
  const html = generateHtml(data, flags);

  const outputPath = path.join(OUTPUT_DIR, "baseline-report.html");
  fs.writeFileSync(outputPath, html);
  console.log(`\nReport generated: ${outputPath}`);

  // Also write pattern flags as JSON for downstream use
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "pattern-flags.json"),
    JSON.stringify(flags, null, 2),
  );
  console.log(`Pattern flags: ${path.join(OUTPUT_DIR, "pattern-flags.json")}`);
}

main();
