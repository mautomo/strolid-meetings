from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class Person(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    role: Optional[str] = None
    department: Optional[str] = None
    meetingCount: int = 0

class Decision(BaseModel):
    id: str
    description: str
    decidedBy: List[str] = Field(default_factory=list)
    meetingId: str
    meetingDate: str
    topic: str
    confidence: Literal["firm", "tentative", "exploratory"]
    supersedes: Optional[str] = None # ID of decision this overrides
    supersededBy: Optional[str] = None # ID of decision that overrides this

class ExpectedOutcome(BaseModel):
    system: str
    description: str

class ActionItem(BaseModel):
    id: str
    task: str
    owner: str
    meetingId: str
    meetingDate: str
    deadline: Optional[str] = None
    status: Literal["open", "done", "abandoned", "recurring"]
    resolvedInMeeting: Optional[str] = None
    expectedOutcome: Optional[ExpectedOutcome] = None

class TopicThread(BaseModel):
    id: str
    label: str
    firstMentioned: str
    lastMentioned: str
    meetingRefs: List[str] = Field(default_factory=list)
    decisionRefs: List[str] = Field(default_factory=list)
    mentionCount: int = 0

class DirectionChange(BaseModel):
    topic: str
    originalPosition: str
    originalDate: str
    originalMeeting: str
    newPosition: str
    changeDate: str
    changeMeeting: str
    daysBetween: int

class ExtractedMeetingDecision(BaseModel):
    description: str
    decidedBy: List[str]
    topic: str
    confidence: Literal["firm", "tentative", "exploratory"]

class ExtractedMeetingActionItem(BaseModel):
    task: str
    owner: str
    deadline: Optional[str] = None
    expectedOutcome: Optional[ExpectedOutcome] = None

class ExtractedMeeting(BaseModel):
    meetingId: str
    title: str
    date: str
    series: str
    type: Literal["leadership", "marketing", "product", "one-on-one", "standup", "strategy", "other"]
    attendees: List[str] = Field(default_factory=list)
    summary: str
    decisions: List[ExtractedMeetingDecision] = Field(default_factory=list)
    actionItems: List[ExtractedMeetingActionItem] = Field(default_factory=list)
    topicsDiscussed: List[str] = Field(default_factory=list)
    tensions: List[str] = Field(default_factory=list)
    referencesToPast: List[str] = Field(default_factory=list)

class NormalizedData(BaseModel):
    people: List[Person] = Field(default_factory=list)
    decisions: List[Decision] = Field(default_factory=list)
    actionItems: List[ActionItem] = Field(default_factory=list)
    topics: List[TopicThread] = Field(default_factory=list)
    directionChanges: List[DirectionChange] = Field(default_factory=list)
    meetings: List[ExtractedMeeting] = Field(default_factory=list)

class PatternFlag(BaseModel):
    type: Literal["inconsistency", "direction_change", "zombie_topic", "orphan_action", "echo_chamber", "recurring_unresolved"]
    severity: Literal["high", "medium", "low"]
    title: str
    description: str
    meetingRefs: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    relatedEntities: List[str] = Field(default_factory=list)

class ExtractedDocument(BaseModel):
    docId: str
    title: str
    date: Optional[str] = None # format YYYY-MM-DD
    authors: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    summary: str
    text: str

