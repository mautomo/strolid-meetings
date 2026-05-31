"use client";

import { Presentation, CalendarRange, Gauge, GitCompareArrows, Brain, type LucideIcon } from "lucide-react";
import { useChat } from "@/context/ChatContext";
import { Markdown } from "@/components/common/Markdown";
import { AssistantAvatar, UserAvatar } from "@/components/common/Avatars";
import type { Artifact, Message } from "@/lib/types";

const ARTIFACT_ICON: Record<Artifact["artifact_type"], LucideIcon> = {
  presentation: Presentation,
  timeline: CalendarRange,
  scorecard: Gauge,
  comparison: GitCompareArrows,
  deepthink: Brain,
};

export function MessageBubble({ message }: { message: Message }) {
  const { setActiveArtifact, setSlideIndex } = useChat();
  const isUser = message.role === "user";

  return (
    <div
      style={{
        display: "flex",
        gap: "0.85rem",
        alignSelf: isUser ? "flex-end" : "flex-start",
        flexDirection: isUser ? "row-reverse" : "row",
        maxWidth: "85%",
        alignItems: "flex-start",
      }}
    >
      {isUser ? <UserAvatar /> : <AssistantAvatar />}

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div
          style={{
            padding: isUser ? "0.7rem 1rem" : "0.1rem 0",
            background: isUser ? "var(--surface-2)" : "transparent",
            border: isUser ? "1px solid var(--hairline)" : "none",
            borderRadius: "var(--radius-panel)",
            color: "var(--foreground)",
            fontSize: "0.95rem",
            lineHeight: 1.6,
            whiteSpace: isUser ? "pre-wrap" : "normal",
          }}
        >
          {isUser ? message.content : <Markdown text={message.content} />}
        </div>

        {message.artifact && (
          <ArtifactCard
            artifact={message.artifact}
            onOpen={() => {
              setActiveArtifact(message.artifact!);
              if (message.artifact!.artifact_type === "presentation") setSlideIndex(0);
            }}
          />
        )}
      </div>
    </div>
  );
}

function ArtifactCard({ artifact, onOpen }: { artifact: Artifact; onOpen: () => void }) {
  const Icon = ARTIFACT_ICON[artifact.artifact_type];
  return (
    <div className="card-reveal" style={{ maxWidth: 320, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <Icon size={16} color="var(--star)" />
        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#fff" }}>{artifact.title}</span>
      </div>
      <span className="t-xs">{artifact.artifact_type}</span>
      <button type="button" className="btn btn-primary btn-sm" style={{ width: "100%" }} onClick={onOpen}>
        Open in canvas
      </button>
    </div>
  );
}
