"use client";

import { useState } from "react";
import {
  CalendarRange,
  Tags,
  LayoutDashboard,
  HeartPulse,
  ChevronLeft,
  Check,
  type LucideIcon,
} from "lucide-react";
import { useChat } from "@/context/ChatContext";
import type { CanvasHint, SentimentMode } from "@/lib/types";
import { CalendarRangePanel } from "./CalendarRangePanel";

type View = "menu" | "calendar" | "topics" | "canvas" | "sentiment";

const CANVAS_OPTIONS: { hint: CanvasHint; label: string; prompt: string }[] = [
  { hint: "timeline", label: "Timeline", prompt: "Build a timeline of key decisions and action items for the selected scope." },
  { hint: "presentation", label: "Presentation", prompt: "Create a presentation summarizing the selected meetings." },
  { hint: "scorecard", label: "Scorecard", prompt: "Generate a reliability scorecard for the selected scope." },
  { hint: "comparison", label: "Comparison", prompt: "Compare alignment between two people on the selected topics." },
];

const SENTIMENT_OPTIONS: { mode: SentimentMode; label: string }[] = [
  { mode: "one_to_one", label: "1 vs 1" },
  { mode: "one_to_all", label: "1 vs all" },
  { mode: "all", label: "All by individual" },
];

export function ToolDrawer({ onClose }: { onClose: () => void }) {
  const { topicsList, selectedTopics, setSelectedTopics, setCanvasHint, setSentimentMode, setInput } = useChat();
  const [view, setView] = useState<View>("menu");

  const toggleTopic = (label: string) =>
    setSelectedTopics(
      selectedTopics.includes(label)
        ? selectedTopics.filter((t) => t !== label)
        : [...selectedTopics, label],
    );

  const pickCanvas = (hint: CanvasHint, prompt: string) => {
    setCanvasHint(hint);
    setInput(prompt);
    onClose();
  };

  const pickSentiment = (mode: SentimentMode) => {
    setSentimentMode(mode);
    setInput("Analyze sentiment for the selected scope.");
    onClose();
  };

  return (
    <div
      role="menu"
      style={{
        position: "absolute",
        bottom: "calc(100% + 0.5rem)",
        left: 0,
        width: 280,
        maxHeight: 360,
        overflowY: "auto",
        padding: "0.5rem",
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-panel)",
        boxShadow: "var(--shadow-3)",
        zIndex: 20,
      }}
    >
      {view === "menu" && (
        <>
          <MenuRow icon={CalendarRange} label="Calendar" onClick={() => setView("calendar")} />
          <MenuRow icon={Tags} label="Topics" onClick={() => setView("topics")} />
          <MenuRow icon={LayoutDashboard} label="Canvas" onClick={() => setView("canvas")} />
          <MenuRow icon={HeartPulse} label="Sentiment" onClick={() => setView("sentiment")} />
        </>
      )}

      {view !== "menu" && (
        <button type="button" className="btn-ghost" onClick={() => setView("menu")} style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.5rem", color: "var(--muted-foreground)", fontSize: "0.8rem", marginBottom: "0.25rem" }}>
          <ChevronLeft size={15} /> Back
        </button>
      )}

      {view === "calendar" && <CalendarRangePanel onDone={onClose} />}

      {view === "topics" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          {topicsList.length === 0 && <p className="t-sm" style={{ padding: "0.5rem" }}>No topics available.</p>}
          {topicsList.map((t) => {
            const on = selectedTopics.includes(t.label);
            return (
              <button key={t.label} type="button" onClick={() => toggleTopic(t.label)} className="btn-ghost" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0.5rem", borderRadius: "var(--radius-base)", color: on ? "#fff" : "var(--muted-foreground)", fontSize: "0.82rem" }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.label}</span>
                {on ? <Check size={15} color="var(--star)" /> : <span className="t-xs">{t.mention_count}</span>}
              </button>
            );
          })}
        </div>
      )}

      {view === "canvas" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          {CANVAS_OPTIONS.map((o) => (
            <MenuRow key={o.hint} icon={LayoutDashboard} label={o.label} onClick={() => pickCanvas(o.hint, o.prompt)} />
          ))}
        </div>
      )}

      {view === "sentiment" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          {SENTIMENT_OPTIONS.map((o) => (
            <MenuRow key={o.mode} icon={HeartPulse} label={o.label} onClick={() => pickSentiment(o.mode)} />
          ))}
          <p className="t-xs" style={{ padding: "0.5rem", letterSpacing: "0.04em" }}>
            Per-person sentiment data arrives in a later phase.
          </p>
        </div>
      )}
    </div>
  );
}

function MenuRow({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button type="button" role="menuitem" onClick={onClick} className="btn-ghost" style={{ display: "flex", alignItems: "center", gap: "0.6rem", width: "100%", padding: "0.5rem 0.6rem", borderRadius: "var(--radius-base)", color: "var(--foreground)", fontSize: "0.85rem" }}>
      <Icon size={17} color="var(--muted-foreground)" />
      {label}
    </button>
  );
}
