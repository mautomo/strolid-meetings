// Shared types for the meeting intelligence pipeline

export interface Person {
  id: string;
  name: string;
  aliases: string[];
  role?: string;
  department?: string;
  meetingCount: number;
}

export interface Decision {
  id: string;
  description: string;
  decidedBy: string[];
  meetingId: string;
  meetingDate: string;
  topic: string;
  confidence: "firm" | "tentative" | "exploratory";
  supersedes?: string; // ID of decision this overrides
  supersededBy?: string; // ID of decision that overrides this
}

export interface ActionItem {
  id: string;
  task: string;
  owner: string;
  meetingId: string;
  meetingDate: string;
  deadline?: string;
  status: "open" | "done" | "abandoned" | "recurring";
  resolvedInMeeting?: string;
  expectedOutcome?: {
    system: string;
    description: string;
  };
}

export interface TopicThread {
  id: string;
  label: string;
  firstMentioned: string;
  lastMentioned: string;
  meetingRefs: string[];
  decisionRefs: string[];
  mentionCount: number;
}

export interface DirectionChange {
  topic: string;
  originalPosition: string;
  originalDate: string;
  originalMeeting: string;
  newPosition: string;
  changeDate: string;
  changeMeeting: string;
  daysBetween: number;
}

export interface ExtractedMeeting {
  meetingId: string;
  title: string;
  date: string;
  series: string;
  type:
    | "leadership"
    | "marketing"
    | "product"
    | "one-on-one"
    | "standup"
    | "strategy"
    | "other";
  attendees: string[];
  summary: string;
  decisions: {
    description: string;
    decidedBy: string[];
    topic: string;
    confidence: "firm" | "tentative" | "exploratory";
  }[];
  actionItems: {
    task: string;
    owner: string;
    deadline?: string;
    expectedOutcome?: {
      system: string;
      description: string;
    };
  }[];
  topicsDiscussed: string[];
  tensions: string[];
  referencesToPast: string[];
}

export interface NormalizedData {
  people: Person[];
  decisions: Decision[];
  actionItems: ActionItem[];
  topics: TopicThread[];
  directionChanges: DirectionChange[];
  meetings: ExtractedMeeting[];
}

export interface PatternFlag {
  type:
    | "inconsistency"
    | "direction_change"
    | "zombie_topic"
    | "orphan_action"
    | "echo_chamber"
    | "recurring_unresolved";
  severity: "high" | "medium" | "low";
  title: string;
  description: string;
  meetingRefs: string[];
  dates: string[];
  relatedEntities: string[];
}
