"use client";

import { LayoutDashboard, X } from "lucide-react";
import { useChat } from "@/context/ChatContext";
import { TimelineArtifact } from "./artifacts/TimelineArtifact";
import { PresentationArtifact } from "./artifacts/PresentationArtifact";
import { ScorecardArtifact } from "./artifacts/ScorecardArtifact";
import { ComparisonArtifact } from "./artifacts/ComparisonArtifact";
import { DeepThinkArtifact } from "./artifacts/DeepThinkArtifact";

export function Canvas() {
  const { activeArtifact, setActiveArtifact } = useChat();
  if (!activeArtifact) return null;

  return (
    <section
      style={{
        width: 480,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        margin: "0.75rem 0.75rem 0.75rem 0",
        padding: "1.5rem",
        background: "var(--surface-1)",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-panel)",
        boxShadow: "var(--shadow-2)",
        height: "calc(100% - 1.5rem)",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
        <span className="badge badge-default">{activeArtifact.artifact_type}</span>
        <button type="button" className="btn-ghost" aria-label="Clear canvas" onClick={() => setActiveArtifact(null)} style={{ padding: 6, borderRadius: "var(--radius-base)" }}>
          <X size={18} />
        </button>
      </div>

      <h2 className="t-l" style={{ color: "#fff", marginBottom: "1.25rem" }}>{activeArtifact.title}</h2>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {activeArtifact.artifact_type === "timeline" && <TimelineArtifact data={activeArtifact} />}
        {activeArtifact.artifact_type === "presentation" && <PresentationArtifact data={activeArtifact} />}
        {activeArtifact.artifact_type === "scorecard" && <ScorecardArtifact data={activeArtifact} />}
        {activeArtifact.artifact_type === "comparison" && <ComparisonArtifact data={activeArtifact} />}
        {activeArtifact.artifact_type === "deepthink" && <DeepThinkArtifact data={activeArtifact} />}
      </div>
    </section>
  );
}

export function EmptyCanvasIcon() {
  return <LayoutDashboard size={40} color="var(--mid-gray)" />;
}
