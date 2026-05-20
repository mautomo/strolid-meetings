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

output_lines = []
output_lines.append("# Vinnie Micciche and Michael Donovan: Relationship Pattern Profile\n")
output_lines.append("**Analysis Date:** " + datetime.now().strftime('%Y-%m-%d') + "\n\n")
output_lines.append("---\n\n")

output_lines.append("## Executive Summary\n\n")
output_lines.append("- **Total Meetings Together:** " + str(analysis['total_meetings']) + "\n")
if analysis['meetings_timeline']:
    output_lines.append("- **Date Range:** " + analysis['meetings_timeline'][0]['date'] + " to " + analysis['meetings_timeline'][-1]['date'] + "\n")
output_lines.append("- **Joint Decisions:** " + str(analysis['decisions_count']['joint']) + "\n")
output_lines.append("- **Vinnie-Led Decisions:** " + str(analysis['decisions_count']['vinnie']) + "\n")
output_lines.append("- **Michael-Led Decisions:** " + str(analysis['decisions_count']['michael']) + "\n")
output_lines.append("- **Decision Alignment Score:** " + str(round(alignment_score, 1)) + "%\n")
output_lines.append("- **Recorded Tensions:** " + str(sum(len(v) for v in analysis['tensions_by_meeting'].values())) + "\n\n")

output_lines.append("## Meeting Timeline and Key Decisions\n\n")
for meeting in analysis['meetings_timeline']:
    output_lines.append("### " + meeting['date'] + " - " + meeting['title'] + "\n\n")
    if meeting['decisions']:
        output_lines.append("Decisions recorded in this meeting.\n\n")
    if meeting['tensions']:
        output_lines.append("**Tensions:**\n")
        for t in meeting['tensions'][:2]:
            output_lines.append("- " + t + "\n")
        output_lines.append("\n")

output_lines.append("## Joint Decisions (Agreements)\n\n")
for d in analysis['joint_decisions']:
    output_lines.append("- " + d['date'] + " (" + d['title'] + "): " + d['decision'][:100] + "...\n")

output_lines.append("\n## Vinnie-Led Decisions\n\n")
for d in analysis['vinnie_decisions'][:15]:
    output_lines.append("- " + d['date'] + ": " + d['decision'][:90] + "...\n")

output_lines.append("\n## Michael-Led Decisions\n\n")
for d in analysis['michael_decisions'][:15]:
    output_lines.append("- " + d['date'] + ": " + d['decision'][:90] + "...\n")

output_lines.append("\n## Topic Ownership\n\n")
output_lines.append("| Topic | Vinnie | Michael | Joint |\n")
output_lines.append("|-------|--------|---------|-------|\n")
for topic, counts in sorted(analysis['topic_ownership'].items(), key=lambda x: sum(x[1].values()), reverse=True)[:12]:
    output_lines.append("| " + topic + " | " + str(counts['vinnie']) + " | " + str(counts['michael']) + " | " + str(counts['joint']) + " |\n")

output_lines.append("\n## Action Items Assigned\n\n")
vinnie_count = len(analysis['action_items']['Vinnie Micciche'])
michael_count = len(analysis['action_items']['Michael Donovan'])
output_lines.append("### Vinnie Micciche (" + str(vinnie_count) + " items)\n\n")
for item in analysis['action_items']['Vinnie Micciche'][:8]:
    output_lines.append("- (" + item['date'] + ") " + item['task'][:80] + "...\n")

output_lines.append("\n### Michael Donovan (" + str(michael_count) + " items)\n\n")
for item in analysis['action_items']['Michael Donovan'][:8]:
    output_lines.append("- (" + item['date'] + ") " + item['task'][:80] + "...\n")

output_lines.append("\n## Tension Points Over Time\n\n")
for date in sorted(analysis['tensions_by_meeting'].keys()):
    tensions = analysis['tensions_by_meeting'][date]
    if tensions:
        output_lines.append("### " + date + "\n\n")
        for t in tensions[:3]:
            output_lines.append("- " + t + "\n")
        output_lines.append("\n")

output_lines.append("## Strategic Direction Changes\n\n")
output_lines.append("**Total: " + str(len(analysis['direction_changes_involving_both'])) + " changes**\n\n")
for change in analysis['direction_changes_involving_both'][:12]:
    output_lines.append("### " + change['topic'] + " (" + change['date'] + ")\n\n")
    output_lines.append("From: " + change['original'][:100] + "...\n\n")
    output_lines.append("To: " + change['new'][:100] + "...\n\n")

output_lines.append("## Power Dynamics Summary\n\n")
output_lines.append("**Vinnie's Role:** Strategic leader, sets direction on messaging and business focus\n\n")
output_lines.append("**Michael's Role:** Marketing executor, implements digital/social strategy\n\n")
output_lines.append("**Decision Pattern:** " + str(round(alignment_score, 1)) + "% alignment (joint decisions)\n\n")
output_lines.append("**Key Insight:** Relationship evolved from strategic alignment (early 2025) to tension (late 2025) to structured meetings (2026)\n\n")

output_lines.append("---\n\n")
output_lines.append("## Data Summary\n\n")
output_lines.append("- Meetings: " + str(analysis['total_meetings']) + "\n")
output_lines.append("- Total Decisions: " + str(sum(analysis['decisions_count'].values())) + "\n")
output_lines.append("- Total Tensions: " + str(sum(len(v) for v in analysis['tensions_by_meeting'].values())) + "\n")
output_lines.append("- Direction Changes: " + str(len(analysis['direction_changes_involving_both'])) + "\n")

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(''.join(output_lines))

print("SUCCESS: Report generated")
print("Meetings: " + str(analysis['total_meetings']))
print("Alignment: " + str(round(alignment_score, 1)) + "%")
