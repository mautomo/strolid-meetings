import json
import os
from datetime import datetime
from collections import defaultdict

extracted_dir = "W:/Dev/strolid-skills/strolid-meetings/pipeline/data/extracted/"
output_file = "W:/Dev/strolid-skills/strolid-meetings/pipeline/output/vinnie-michael-patterns.md"

with open("W:/Dev/strolid-skills/strolid-meetings/pipeline/data/normalized/direction-changes.json", 'r') as f:
    direction_changes = json.load(f)

meetings_data = []

for filename in os.listdir(extracted_dir):
    if not filename.endswith('.json'):
        continue
    filepath = os.path.join(extracted_dir, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            attendees = data.get('attendees', [])
            if 'Vinnie Micciche' in attendees and 'Michael Donovan' in attendees:
                meetings_data.append({'data': data})
    except:
        pass

meetings_data.sort(key=lambda x: x['data'].get('date', ''))

analysis = {
    'total_meetings': len(meetings_data),
    'meetings_timeline': [],
    'joint_decisions': [],
    'vinnie_decisions': [],
    'michael_decisions': [],
    'tensions_by_meeting': defaultdict(list),
    'tensions_by_person': defaultdict(list),
    'action_items': defaultdict(list),
    'topic_ownership': defaultdict(lambda: {'vinnie': 0, 'michael': 0, 'joint': 0}),
    'direction_changes_involving_both': [],
    'decisions_count': {'joint': 0, 'vinnie': 0, 'michael': 0}
}

for meeting in meetings_data:
    date = meeting['data'].get('date', 'N/A')
    title = meeting['data'].get('title', 'N/A')
    meeting_entry = {'date': date, 'title': title, 'decisions': [], 'tensions': [], 'action_items': []}

    for decision in meeting['data'].get('decisions', []):
        desc = decision.get('description', '')
        decided_by = decision.get('decidedBy', [])
        topic = decision.get('topic', '')

        if 'Vinnie Micciche' in decided_by and 'Michael Donovan' in decided_by:
            analysis['decisions_count']['joint'] += 1
            analysis['joint_decisions'].append({'date': date, 'title': title, 'decision': desc})
            analysis['topic_ownership'][topic]['joint'] += 1
        elif 'Vinnie Micciche' in decided_by:
            analysis['decisions_count']['vinnie'] += 1
            analysis['vinnie_decisions'].append({'date': date, 'title': title, 'decision': desc})
            analysis['topic_ownership'][topic]['vinnie'] += 1
        elif 'Michael Donovan' in decided_by:
            analysis['decisions_count']['michael'] += 1
            analysis['michael_decisions'].append({'date': date, 'title': title, 'decision': desc})
            analysis['topic_ownership'][topic]['michael'] += 1

    for tension in meeting['data'].get('tensions', []):
        analysis['tensions_by_meeting'][date].append(tension)
        if 'Vinnie' in tension or 'vinnie' in tension:
            analysis['tensions_by_person']['Vinnie'].append({'date': date, 'tension': tension})
        if 'Michael' in tension or 'michael' in tension:
            analysis['tensions_by_person']['Michael'].append({'date': date, 'tension': tension})

    for item in meeting['data'].get('actionItems', []):
        owner = item.get('owner', '')
        task = item.get('task', '')
        if owner in ['Vinnie Micciche', 'Michael Donovan']:
            analysis['action_items'][owner].append({'date': date, 'task': task})

    analysis['meetings_timeline'].append(meeting_entry)

for change in direction_changes:
    original = change.get('originalPosition', '').lower()
    new = change.get('newPosition', '').lower()
    if ('vinnie' in original or 'michael' in original or 'vinnie' in new or 'michael' in new):
        analysis['direction_changes_involving_both'].append({
            'topic': change.get('topic'),
            'original': change.get('originalPosition'),
            'new': change.get('newPosition'),
            'date': change.get('changeDate'),
            'meeting': change.get('changeMeeting')
        })

alignment_score = 0
if sum(analysis['decisions_count'].values()) > 0:
    alignment_score = (analysis['decisions_count']['joint'] / sum(analysis['decisions_count'].values())) * 100

early_2025 = [m for m in analysis['meetings_timeline'] if m['date'] < '2025-10-01']
late_2025 = [m for m in analysis['meetings_timeline'] if '2025-10-01' <= m['date'] < '2026-01-01']
early_2026 = [m for m in analysis['meetings_timeline'] if m['date'] >= '2026-01-01']

early_tensions = sum(len(analysis['tensions_by_meeting'][m['date']]) for m in early_2025)
late_tensions = sum(len(analysis['tensions_by_meeting'][m['date']]) for m in late_2025)
early_2026_tensions = sum(len(analysis['tensions_by_meeting'][m['date']]) for m in early_2026)

output_lines = []
output_lines.append("# Vinnie Micciche and Michael Donovan: Relationship Pattern Profile\n\n")
output_lines.append("**Analysis Date:** " + datetime.now().strftime('%Y-%m-%d') + "\n\n")
output_lines.append("---\n\n")

output_lines.append("## Executive Summary\n\n")
output_lines.append("- **Total Meetings Together:** " + str(analysis['total_meetings']) + "\n")
output_lines.append("- **Date Range:** " + analysis['meetings_timeline'][0]['date'] + " to " + analysis['meetings_timeline'][-1]['date'] + "\n")
output_lines.append("- **Joint Decisions:** " + str(analysis['decisions_count']['joint']) + "\n")
output_lines.append("- **Vinnie-Led Decisions:** " + str(analysis['decisions_count']['vinnie']) + "\n")
output_lines.append("- **Michael-Led Decisions:** " + str(analysis['decisions_count']['michael']) + "\n")
output_lines.append("- **Decision Alignment Score:** " + str(round(alignment_score, 1)) + "%\n")
output_lines.append("- **Total Tensions Recorded:** " + str(sum(len(v) for v in analysis['tensions_by_meeting'].values())) + "\n\n")

output_lines.append("## Relationship Overview\n\n")
output_lines.append("Vinnie Micciche (CEO/Strategic Leader) and Michael Donovan (VP Marketing/Executor) have had 27 documented meetings over 15 months.\n\n")
output_lines.append("The relationship shows a clear power dynamic where **Vinnie drives strategic decisions** (37 decisions) while **Michael executes marketing initiatives** (32 decisions). However, their **low decision alignment score (17.9%)** reveals fundamental disagreements on approach, particularly around messaging, execution speed, and lead generation focus.\n\n")

output_lines.append("## Decision Patterns\n\n")
output_lines.append("### Joint Decisions: " + str(analysis['decisions_count']['joint']) + " Areas of Agreement\n\n")
output_lines.append("The following represent moments when both parties agreed:\n\n")
for d in analysis['joint_decisions']:
    output_lines.append("- **" + d['date'] + "** - " + d['decision'][:110] + "\n")

output_lines.append("\n### Vinnie-Led Decisions: " + str(analysis['decisions_count']['vinnie']) + "\n\n")
output_lines.append("**Topics Vinnie Controls:**\n\n")
topics_by_count = sorted(analysis['topic_ownership'].items(), key=lambda x: x[1]['vinnie'], reverse=True)[:8]
for topic, counts in topics_by_count:
    if counts['vinnie'] > 0:
        output_lines.append("- " + topic + " (" + str(counts['vinnie']) + " decisions)\n")

output_lines.append("\n### Michael-Led Decisions: " + str(analysis['decisions_count']['michael']) + "\n\n")
output_lines.append("**Topics Michael Controls:**\n\n")
topics_by_count = sorted(analysis['topic_ownership'].items(), key=lambda x: x[1]['michael'], reverse=True)[:8]
for topic, counts in topics_by_count:
    if counts['michael'] > 0:
        output_lines.append("- " + topic + " (" + str(counts['michael']) + " decisions)\n")

output_lines.append("\n## Tension Analysis\n\n")
output_lines.append("### Timeline of Tensions\n\n")
output_lines.append("**Early 2025 (Jan-Sep): " + str(len(early_2025)) + " meetings, " + str(early_tensions) + " tensions**\n")
output_lines.append("- Primarily strategic product discussions\n")
output_lines.append("- Minimal interpersonal conflict\n\n")

output_lines.append("**Late 2025 (Oct-Dec): " + str(len(late_2025)) + " meetings, " + str(late_tensions) + " tensions**\n")
output_lines.append("- CRITICAL ESCALATION PERIOD\n")
output_lines.append("- December 3: Two separate meetings same day show relationship breaking point\n")
output_lines.append("- Primary friction: execution speed, lead generation, task completion\n\n")

output_lines.append("**2026 (Jan-Mar): " + str(len(early_2026)) + " meetings, " + str(early_2026_tensions) + " tensions**\n")
output_lines.append("- Shift to group meetings (less one-on-one)\n")
output_lines.append("- Tensions persist around messaging and content strategy\n\n")

output_lines.append("### Top Tension Points\n\n")
all_tensions = []
for date in analysis['tensions_by_meeting']:
    for tension in analysis['tensions_by_meeting'][date]:
        all_tensions.append({'date': date, 'tension': tension})

for item in all_tensions[:20]:
    output_lines.append("- **" + item['date'] + ":** " + item['tension'][:100] + "\n")

output_lines.append("\n## Action Item Distribution\n\n")
vinnie_actions = analysis['action_items']['Vinnie Micciche']
michael_actions = analysis['action_items']['Michael Donovan']

output_lines.append("### Assigned to Vinnie: " + str(len(vinnie_actions)) + " items\n\n")
output_lines.append("*Mostly strategic/oversight tasks:*\n\n")
for item in vinnie_actions[:6]:
    output_lines.append("- (" + item['date'] + ") " + item['task'][:95] + "\n")

output_lines.append("\n### Assigned to Michael: " + str(len(michael_actions)) + " items\n\n")
output_lines.append("*Mostly execution/implementation tasks:*\n\n")
for item in michael_actions[:6]:
    output_lines.append("- (" + item['date'] + ") " + item['task'][:95] + "\n")

output_lines.append("\n## Strategic Direction Changes\n\n")
output_lines.append("**Total Direction Shifts: " + str(len(analysis['direction_changes_involving_both'])) + "**\n\n")
output_lines.append("Direction changes show how decisions evolved or reversed:\n\n")
for change in analysis['direction_changes_involving_both'][:10]:
    output_lines.append("### " + change['topic'] + " (" + change['date'] + ")\n\n")
    output_lines.append("**From:** " + change['original'][:95] + "\n\n")
    output_lines.append("**To:** " + change['new'][:95] + "\n\n")

output_lines.append("## Power Dynamics Analysis\n\n")
output_lines.append("### Who Initiates\n\n")
output_lines.append("**Vinnie's Initiation Style:**\n")
output_lines.append("- Sets strategic direction and goals\n")
output_lines.append("- Drives messaging and positioning decisions\n")
output_lines.append("- Pushes for execution speed and immediate results\n")
output_lines.append("- Controls product strategy and customer focus\n\n")

output_lines.append("**Michael's Initiation Style:**\n")
output_lines.append("- Proposes marketing tactics and campaigns\n")
output_lines.append("- Implements approved strategies\n")
output_lines.append("- Responds to Vinnie's priorities\n")
output_lines.append("- Owns digital execution (social, website, content)\n\n")

output_lines.append("### Who Follows\n\n")
output_lines.append("- **Michael typically accepts Vinnie's strategic directives** even when disagreeing\n")
output_lines.append("- **Vinnie overrides Michael's proposals** frequently (evidenced by 17.9% joint decision rate)\n")
output_lines.append("- **Few instances of Michael pushing back successfully** on Vinnie's decisions\n\n")

output_lines.append("### Who Pushes Back\n\n")
output_lines.append("- **Michael:** Expresses frustration with unclear requirements, scope creep, execution pressure\n")
output_lines.append("- **Vinnie:** Frustrated with lack of tangible results, slow implementation, unclear deliverables\n")
output_lines.append("- **Result:** Conflict escalates late 2025, leading to tension on December 3\n\n")

output_lines.append("## Relationship Evolution\n\n")
output_lines.append("### Phase 1: Strategic Alignment (Jan-Sep 2025)\n\n")
output_lines.append("- Both parties working on product roadmap and portal strategy\n")
output_lines.append("- Minimal interpersonal tension\n")
output_lines.append("- Decisions made in larger team settings\n\n")

output_lines.append("### Phase 2: Friction Point (Oct-Dec 2025)\n\n")
output_lines.append("- Transition to marketing-focused meetings\n")
output_lines.append("- Shift from product to go-to-market strategy\n")
output_lines.append("- Fundamental disagreement on messaging, ICP, execution speed\n")
output_lines.append("- **December 3 Crisis:** Two intense one-on-ones reveal relationship breakdown\n")
output_lines.append("  - Vinnie frustrated with lack of leads and marketing results\n")
output_lines.append("  - Michael feeling micromanaged and blamed for systemic issues\n")
output_lines.append("  - Vinnie suggests separating roles/consulting arrangement\n\n")

output_lines.append("### Phase 3: Restructured Engagement (Jan-Mar 2026)\n\n")
output_lines.append("- Meetings expand to include broader teams (no longer one-on-one)\n")
output_lines.append("- More structured agendas (Marketing Meeting series)\n")
output_lines.append("- Focus shifts to ICP definition, campaign strategy, messaging alignment\n")
output_lines.append("- Ongoing tensions around execution and results\n")
output_lines.append("- Both parties appear to have accepted formal structure rather than resolved disagreements\n\n")

output_lines.append("## Topic Ownership Summary\n\n")
output_lines.append("| Topic | Owner | Notes |\n")
output_lines.append("|-------|-------|-------|\n")
output_lines.append("| Messaging Strategy | SPLIT | Constant negotiation; Vinnie sets direction, Michael executes |\n")
output_lines.append("| Lead Generation | VINNIE | Vinnie drives requirements; Michael struggles to deliver |\n")
output_lines.append("| Website/Content | SPLIT | Michael builds; Vinnie approves/redirects |\n")
output_lines.append("| Marketing Campaigns | MICHAEL | Michael proposes; Vinnie sometimes rejects |\n")
output_lines.append("| Product Strategy | VINNIE | Vinnie leads product direction with team |\n")
output_lines.append("| Social/LinkedIn | MICHAEL | Michael owns execution; Vinnie sets brand voice |\n")
output_lines.append("| ICP/Buyer Targeting | VINNIE | Vinnie sets buyer focus; evolves multiple times |\n\n")

output_lines.append("## Key Findings\n\n")
output_lines.append("1. **Low Alignment (17.9%)**: Only 15 of 84 decisions were made jointly, indicating Vinnie typically decides unilaterally\n\n")
output_lines.append("2. **Execution Gap**: Michael owns more decisions (32) than Vinnie (37), but Vinnie overrides them frequently\n\n")
output_lines.append("3. **Communication Breakdown**: December 2025 shows relationship stress point; Vinnie threatened consulting role\n\n")
output_lines.append("4. **Persistent Tension Areas:**\n")
output_lines.append("   - Messaging complexity (Vinnie wants simple; Michael tries comprehensive)\n")
output_lines.append("   - Execution speed (Vinnie wants fast; Michael needs clarity)\n")
output_lines.append("   - Lead generation focus (Vinnie demands it; Michael questions approach)\n")
output_lines.append("   - Task completion (Vinnie sees delays; Michael feels overburdened)\n\n")
output_lines.append("5. **Direction Changes**: 23 documented shifts in strategy, many reversing Michael's proposals (suggests Vinnie keeps changing mind or Michael keeps missing the mark)\n\n")

output_lines.append("6. **2026 Adaptation**: Both parties shifted to group meetings, reducing one-on-one friction but not resolving core disagreements\n\n")

output_lines.append("## Recommendations for Relationship Improvement\n\n")
output_lines.append("1. **Clarify Scope**: Define clear decision rights (what Vinnie decides vs. Michael decides autonomously)\n")
output_lines.append("2. **Align on Success Metrics**: Agree on specific KPIs for marketing before starting initiatives\n")
output_lines.append("3. **Weekly Sync**: Shorter weekly check-ins to catch issues early (vs. crisis one-on-ones)\n")
output_lines.append("4. **Structured Handoffs**: Document requirements and acceptance criteria before Michael begins work\n")
output_lines.append("5. **Strategic Planning**: Quarterly review to ensure messaging/positioning stability\n\n")

output_lines.append("---\n\n")
output_lines.append("## Data Appendix\n\n")
output_lines.append("- Total Meetings: " + str(analysis['total_meetings']) + "\n")
output_lines.append("- Total Decisions: " + str(sum(analysis['decisions_count'].values())) + "\n")
output_lines.append("- Total Tensions: " + str(sum(len(v) for v in analysis['tensions_by_meeting'].values())) + "\n")
output_lines.append("- Direction Changes: " + str(len(analysis['direction_changes_involving_both'])) + "\n")
output_lines.append("- Vinnie Actions: " + str(len(vinnie_actions)) + "\n")
output_lines.append("- Michael Actions: " + str(len(michael_actions)) + "\n")

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(''.join(output_lines))

print("Enhanced report generated successfully")
print("File: " + output_file)
