// Mirrors the backend artifact payloads (chatbot/agent.py generators + server.py Pydantic models).

export type ArtifactType =
  | "timeline"
  | "presentation"
  | "scorecard"
  | "comparison";

export interface TimelineEvent {
  id: string;
  date: string;
  type: string; // "decision" | "action_item" | (future) "document"
  summary: string;
  details?: string;
  meeting_id?: string;
}

export interface TimelineArtifact {
  artifact_type: "timeline";
  title: string;
  events: TimelineEvent[];
}

export interface PresentationSlide {
  id: string;
  layout?: string; // "hero" | "bullets" | "paragraphs"
  title: string;
  subtitle?: string;
  bullets?: string[];
  content?: string;
}

export interface PresentationArtifact {
  artifact_type: "presentation";
  title: string;
  theme?: string;
  slides: PresentationSlide[];
}

export interface ScorecardArtifact {
  artifact_type: "scorecard";
  title: string;
  target?: string;
  reliability: number;
  stats: { completed: number; open: number; delayed: number; abandoned: number };
  top_topics?: string[];
  key_insights?: string[];
}

export interface ComparisonArtifact {
  artifact_type: "comparison";
  title: string;
  entity_a: string;
  entity_b: string;
  joint_decisions: number;
  alignment_score: number;
  contrasting_viewpoints?: string[];
  key_findings?: string[];
}

export type Artifact =
  | TimelineArtifact
  | PresentationArtifact
  | ScorecardArtifact
  | ComparisonArtifact;

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifact?: Artifact;
  timestamp?: unknown;
}

export interface Meeting {
  meeting_id: string;
  date: string;
  title?: string;
}

export interface Stats {
  meetings_count: number;
  decisions_count: number;
}

export interface Topic {
  label: string;
  mention_count: number;
}

export type CanvasHint = "timeline" | "presentation" | "scorecard" | "comparison";
export type SentimentMode = "one_to_one" | "one_to_all" | "all";

export type Role = "admin" | "user";

export interface Me {
  email: string | null;
  role: Role;
  allowlist_enforced: boolean;
}

export interface Member {
  email: string;
  role: Role;
  status: string;
  invitedBy?: string | null;
  createdAt?: string | null;
}

export interface Scope {
  startDate?: string | null;
  endDate?: string | null;
  meetingIds?: string[];
  topics?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  ownerEmail: string | null;
  sharedWith: string[];
  scope: Scope;
  isOwner: boolean;
  updatedAt: string | null;
}

export interface ChatRequestBody {
  session_id: string;
  user_id: string;
  message: string;
  start_date: string | null;
  end_date: string | null;
  selected_meeting_ids: string[] | null;
  topics: string[] | null;
  canvas_hint: CanvasHint | null;
  sentiment_mode: SentimentMode | null;
}

export type SSEEvent =
  | { type: "token"; text: string }
  | { type: "artifact"; payload: Artifact }
  | { type: "error"; message: string }
  | { type: "done" };
