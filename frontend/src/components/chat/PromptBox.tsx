"use client";

import { useState } from "react";
import { AlertCircle, ArrowUp, Plus, X } from "lucide-react";
import { useChat } from "@/context/ChatContext";
import { ToolDrawer } from "./tools/ToolDrawer";

export function PromptBox() {
  const {
    input,
    setInput,
    isStreaming,
    sendMessage,
    chatError,
    dismissError,
    retryLast,
    selectedTopics,
    setSelectedTopics,
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    canvasHint,
    setCanvasHint,
    sentimentMode,
    setSentimentMode,
    isOwnerOfActive,
  } = useChat();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const readOnly = !isOwnerOfActive;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input;
    setInput("");
    await sendMessage(text);
  };

  const hasChips =
    selectedTopics.length > 0 ||
    Boolean(startDate && endDate) ||
    Boolean(canvasHint) ||
    Boolean(sentimentMode);

  return (
    <footer style={{ padding: "1.25rem 2rem 1.5rem", borderTop: "1px solid var(--hairline)" }}>
      {chatError && (
        <div
          style={{
            maxWidth: 760,
            margin: "0 auto 0.75rem",
            padding: "0.7rem 1rem",
            background: "rgba(208, 14, 17, 0.08)",
            border: "1px solid var(--destructive)",
            borderRadius: "var(--radius-base)",
            color: "var(--destructive)",
            fontSize: "0.85rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            {chatError}
          </span>
          <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
            <button type="button" className="btn btn-outline btn-sm" disabled={isStreaming} onClick={retryLast}>
              Retry
            </button>
            <button type="button" className="btn-ghost" aria-label="Dismiss error" onClick={dismissError} style={{ padding: 4, color: "var(--destructive)" }}>
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        {hasChips && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.6rem" }}>
            {startDate && endDate && (
              <Chip label={`${startDate} to ${endDate}`} onClear={() => { setStartDate(""); setEndDate(""); }} />
            )}
            {selectedTopics.map((t) => (
              <Chip key={t} label={t} onClear={() => setSelectedTopics(selectedTopics.filter((x) => x !== t))} />
            ))}
            {canvasHint && <Chip label={`canvas: ${canvasHint}`} onClear={() => setCanvasHint(null)} />}
            {sentimentMode && <Chip label={`sentiment: ${sentimentMode.replace(/_/g, " ")}`} onClear={() => setSentimentMode(null)} />}
          </div>
        )}

        <form onSubmit={submit} style={{ position: "relative" }}>
          {drawerOpen && <ToolDrawer onClose={() => setDrawerOpen(false)} />}

          <button
            type="button"
            aria-label="Tools"
            aria-expanded={drawerOpen}
            disabled={readOnly}
            onClick={() => setDrawerOpen((v) => !v)}
            className={drawerOpen ? "btn-secondary" : "btn-ghost"}
            style={{
              position: "absolute",
              left: 8,
              top: "50%",
              transform: "translateY(-50%)",
              width: 36,
              height: 36,
              borderRadius: "var(--radius-base)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--muted-foreground)",
            }}
          >
            <Plus size={18} />
          </button>

          <input
            type="text"
            placeholder={readOnly ? "Read-only conversation shared with you. Start a new chat to ask your own questions." : "Ask about alignment, timelines, or generate a presentation..."}
            value={input}
            disabled={readOnly}
            onChange={(e) => setInput(e.target.value)}
            style={{
              width: "100%",
              padding: "0.9rem 3.5rem",
              borderRadius: "var(--radius-panel)",
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              fontSize: "0.95rem",
            }}
          />

          <button
            type="submit"
            disabled={isStreaming || !input.trim() || readOnly}
            aria-label="Send"
            className={input.trim() ? "btn-primary" : ""}
            style={{
              position: "absolute",
              right: 8,
              top: "50%",
              transform: "translateY(-50%)",
              width: 36,
              height: 36,
              borderRadius: "var(--radius-base)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: input.trim() ? undefined : "var(--surface-4)",
              color: input.trim() ? "#050505" : "var(--mid-gray)",
            }}
          >
            <ArrowUp size={18} />
          </button>
        </form>
      </div>
    </footer>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="badge badge-signal" style={{ gap: "0.35rem" }}>
      {label}
      <button type="button" aria-label={`Remove ${label}`} onClick={onClear} style={{ background: "transparent", color: "inherit", display: "flex", padding: 0 }}>
        <X size={12} />
      </button>
    </span>
  );
}
