import * as fs from "node:fs";
import * as path from "node:path";
import type {
  ActionItem,
  Decision,
  DirectionChange,
  ExtractedMeeting,
  NormalizedData,
  Person,
  TopicThread,
} from "./types.js";

const EXTRACTED_DIR = path.resolve(import.meta.dirname, "../data/extracted");
const OUTPUT_DIR = path.resolve(import.meta.dirname, "../data/normalized");

// Name aliases for deduplication
const NAME_ALIASES: Record<string, string> = {
  vin: "Vinnie Micciche",
  vinnie: "Vinnie Micciche",
  "vinnie m": "Vinnie Micciche",
  "vinnie micciche": "Vinnie Micciche",
  michael: "Michael Donovan",
  "michael d": "Michael Donovan",
  "michael donovan": "Michael Donovan",
  joe: "Joe Furnari",
  "joe f": "Joe Furnari",
  "joe furnari": "Joe Furnari",
  jason: "Jason Branham",
  "jason branham": "Jason Branham",
  matt: "Matt Watson",
  "matt watson": "Matt Watson",
  paulo: "Paulo Trovao",
  "paulo trovao": "Paulo Trovao",
  shawna: "Shawna Behen",
  "shawna behen": "Shawna Behen",
  thomas: "Thomas Howe",
  "thomas howe": "Thomas Howe",
  sergey: "Sergey",
  sophia: "Sophia",
  jake: "Jake",
  link: "Link",
};

function resolveName(name: string): string {
  const key = name.trim().toLowerCase();
  return NAME_ALIASES[key] || name.trim();
}

function makePersonId(name: string): string {
  return name.toLowerCase().replace(/[^a-z]+/g, "-");
}

function loadExtractedMeetings(): ExtractedMeeting[] {
  const files = fs
    .readdirSync(EXTRACTED_DIR)
    .filter((f) => f.endsWith(".json"));
  const meetings: ExtractedMeeting[] = [];

  for (const file of files) {
    const data = JSON.parse(
      fs.readFileSync(path.join(EXTRACTED_DIR, file), "utf-8"),
    ) as ExtractedMeeting;
    meetings.push(data);
  }

  // Sort chronologically
  meetings.sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
  return meetings;
}

function buildPeople(meetings: ExtractedMeeting[]): Person[] {
  const peopleMap = new Map<string, Person>();

  for (const meeting of meetings) {
    for (const rawName of meeting.attendees) {
      const name = resolveName(rawName);
      const id = makePersonId(name);

      if (!peopleMap.has(id)) {
        peopleMap.set(id, {
          id,
          name,
          aliases: [],
          meetingCount: 0,
        });
      }

      const person = peopleMap.get(id)!;
      person.meetingCount++;

      // Track aliases
      const trimmed = rawName.trim();
      if (trimmed !== name && !person.aliases.includes(trimmed)) {
        person.aliases.push(trimmed);
      }
    }
  }

  // Infer roles/departments from meeting attendance patterns
  for (const person of peopleMap.values()) {
    const attendedTypes = new Set<string>();
    for (const meeting of meetings) {
      if (meeting.attendees.some((a) => resolveName(a) === person.name)) {
        attendedTypes.add(meeting.type);
      }
    }

    if (attendedTypes.has("leadership")) {
      person.department = "leadership";
    } else if (
      attendedTypes.has("marketing") &&
      !attendedTypes.has("product")
    ) {
      person.department = "marketing";
    } else if (
      attendedTypes.has("product") &&
      !attendedTypes.has("marketing")
    ) {
      person.department = "product";
    } else {
      person.department = "cross-functional";
    }
  }

  return Array.from(peopleMap.values()).sort(
    (a, b) => b.meetingCount - a.meetingCount,
  );
}

function buildDecisions(meetings: ExtractedMeeting[]): Decision[] {
  const decisions: Decision[] = [];
  let counter = 1;

  for (const meeting of meetings) {
    for (const d of meeting.decisions) {
      decisions.push({
        id: `d-${String(counter++).padStart(3, "0")}`,
        description: d.description,
        decidedBy: d.decidedBy.map(resolveName),
        meetingId: meeting.meetingId,
        meetingDate: meeting.date,
        topic: d.topic,
        confidence: d.confidence,
      });
    }
  }

  // Chain decisions: find supersedes relationships within same topic
  const byTopic = new Map<string, Decision[]>();
  for (const d of decisions) {
    if (!byTopic.has(d.topic)) byTopic.set(d.topic, []);
    byTopic.get(d.topic)!.push(d);
  }

  for (const [, topicDecisions] of byTopic) {
    if (topicDecisions.length < 2) continue;

    // Sort by date
    topicDecisions.sort(
      (a, b) =>
        new Date(a.meetingDate).getTime() - new Date(b.meetingDate).getTime(),
    );

    // Mark later decisions as superseding earlier ones in same topic
    for (let i = 1; i < topicDecisions.length; i++) {
      const prev = topicDecisions[i - 1];
      const curr = topicDecisions[i];

      // Only link if they seem to modify/override the previous direction
      if (prev.description.toLowerCase() !== curr.description.toLowerCase()) {
        curr.supersedes = prev.id;
        prev.supersededBy = curr.id;
      }
    }
  }

  return decisions;
}

function buildActionItems(meetings: ExtractedMeeting[]): ActionItem[] {
  const items: ActionItem[] = [];
  let counter = 1;

  for (const meeting of meetings) {
    for (const ai of meeting.actionItems) {
      items.push({
        id: `a-${String(counter++).padStart(3, "0")}`,
        task: ai.task,
        owner: resolveName(ai.owner),
        meetingId: meeting.meetingId,
        meetingDate: meeting.date,
        deadline: ai.deadline || undefined,
        status: "open",
        expectedOutcome: ai.expectedOutcome || undefined,
      });
    }
  }

  // Cross-reference: check if action items get mentioned as completed in later meetings
  for (const item of items) {
    const itemWords = item.task
      .toLowerCase()
      .split(/\s+/)
      .filter((w) => w.length > 4);
    const itemDate = new Date(item.meetingDate).getTime();

    for (const meeting of meetings) {
      const meetingDate = new Date(meeting.date).getTime();
      if (meetingDate <= itemDate) continue;

      // Check if this meeting references completion of the task
      const meetingText = [
        meeting.summary,
        ...meeting.referencesToPast,
        ...meeting.decisions.map((d) => d.description),
      ]
        .join(" ")
        .toLowerCase();

      const matchCount = itemWords.filter((w) =>
        meetingText.includes(w),
      ).length;
      if (matchCount >= 3) {
        // Likely referenced in a later meeting
        if (
          meetingText.includes("completed") ||
          meetingText.includes("done") ||
          meetingText.includes("finished") ||
          meetingText.includes("launched") ||
          meetingText.includes("shipped")
        ) {
          item.status = "done";
          item.resolvedInMeeting = meeting.meetingId;
          break;
        }
      }
    }

    // If never referenced in any later meeting and older than 60 days, mark as abandoned
    if (item.status === "open") {
      const daysSince =
        (Date.now() - new Date(item.meetingDate).getTime()) /
        (1000 * 60 * 60 * 24);
      if (daysSince > 60) {
        // Check if the task keeps appearing (recurring)
        const laterMentions = meetings.filter((m) => {
          if (
            new Date(m.date).getTime() <= new Date(item.meetingDate).getTime()
          )
            return false;
          const text = m.actionItems
            .map((a) => a.task)
            .join(" ")
            .toLowerCase();
          const words = item.task
            .toLowerCase()
            .split(/\s+/)
            .filter((w) => w.length > 4);
          return words.filter((w) => text.includes(w)).length >= 3;
        });

        if (laterMentions.length >= 2) {
          item.status = "recurring";
        } else if (laterMentions.length === 0) {
          item.status = "abandoned";
        }
      }
    }
  }

  return items;
}

function buildTopics(
  meetings: ExtractedMeeting[],
  decisions: Decision[],
): TopicThread[] {
  const topicMap = new Map<string, TopicThread>();

  for (const meeting of meetings) {
    for (const topic of meeting.topicsDiscussed) {
      if (!topicMap.has(topic)) {
        topicMap.set(topic, {
          id: topic,
          label: topic,
          firstMentioned: meeting.date,
          lastMentioned: meeting.date,
          meetingRefs: [],
          decisionRefs: [],
          mentionCount: 0,
        });
      }

      const thread = topicMap.get(topic)!;
      thread.meetingRefs.push(meeting.meetingId);
      thread.lastMentioned = meeting.date;
      thread.mentionCount++;
    }
  }

  // Link decisions to topics
  for (const d of decisions) {
    const thread = topicMap.get(d.topic);
    if (thread) {
      thread.decisionRefs.push(d.id);
    }
  }

  return Array.from(topicMap.values()).sort(
    (a, b) => b.mentionCount - a.mentionCount,
  );
}

function detectDirectionChanges(decisions: Decision[]): DirectionChange[] {
  const changes: DirectionChange[] = [];

  const byTopic = new Map<string, Decision[]>();
  for (const d of decisions) {
    if (!byTopic.has(d.topic)) byTopic.set(d.topic, []);
    byTopic.get(d.topic)!.push(d);
  }

  for (const [topic, topicDecisions] of byTopic) {
    if (topicDecisions.length < 2) continue;

    topicDecisions.sort(
      (a, b) =>
        new Date(a.meetingDate).getTime() - new Date(b.meetingDate).getTime(),
    );

    for (let i = 1; i < topicDecisions.length; i++) {
      const prev = topicDecisions[i - 1];
      const curr = topicDecisions[i];

      if (curr.supersedes === prev.id) {
        const daysBetween = Math.round(
          (new Date(curr.meetingDate).getTime() -
            new Date(prev.meetingDate).getTime()) /
            (1000 * 60 * 60 * 24),
        );

        changes.push({
          topic,
          originalPosition: prev.description,
          originalDate: prev.meetingDate,
          originalMeeting: prev.meetingId,
          newPosition: curr.description,
          changeDate: curr.meetingDate,
          changeMeeting: curr.meetingId,
          daysBetween,
        });
      }
    }
  }

  return changes.sort(
    (a, b) =>
      new Date(a.changeDate).getTime() - new Date(b.changeDate).getTime(),
  );
}

function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log("Loading extracted meetings...");
  const meetings = loadExtractedMeetings();
  console.log(`Loaded ${meetings.length} meetings.\n`);

  console.log("Building people index...");
  const people = buildPeople(meetings);
  console.log(`  Found ${people.length} unique people.\n`);

  console.log("Building decision log...");
  const decisions = buildDecisions(meetings);
  console.log(`  Found ${decisions.length} decisions.\n`);

  console.log("Building action item tracker...");
  const actionItems = buildActionItems(meetings);
  const statusCounts = actionItems.reduce(
    (acc, ai) => {
      acc[ai.status] = (acc[ai.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );
  console.log(
    `  Found ${actionItems.length} action items:`,
    statusCounts,
    "\n",
  );

  console.log("Building topic threads...");
  const topics = buildTopics(meetings, decisions);
  console.log(`  Found ${topics.length} unique topics.\n`);

  console.log("Detecting direction changes...");
  const directionChanges = detectDirectionChanges(decisions);
  console.log(`  Found ${directionChanges.length} direction changes.\n`);

  const normalized: NormalizedData = {
    people,
    decisions,
    actionItems,
    topics,
    directionChanges,
    meetings,
  };

  // Write individual files for easy access
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "people.json"),
    JSON.stringify(people, null, 2),
  );
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "decisions.json"),
    JSON.stringify(decisions, null, 2),
  );
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "actions.json"),
    JSON.stringify(actionItems, null, 2),
  );
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "topics.json"),
    JSON.stringify(topics, null, 2),
  );
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "direction-changes.json"),
    JSON.stringify(directionChanges, null, 2),
  );
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "meetings.json"),
    JSON.stringify(meetings, null, 2),
  );

  // Write combined file
  fs.writeFileSync(
    path.join(OUTPUT_DIR, "all.json"),
    JSON.stringify(normalized, null, 2),
  );

  console.log("Normalization complete.");
  console.log(`Output: ${OUTPUT_DIR}`);
}

main();
