"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/context/ChatContext";
import { Markdown } from "@/components/common/Markdown";
import { AssistantAvatar } from "@/components/common/Avatars";
import { MessageBubble } from "./MessageBubble";

export function MessageList() {
  const { messages, isStreaming, streamText } = useChat();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages, streamText, isStreaming]);

  return (
    <div
      ref={containerRef}
      style={{ flex: 1, overflowY: "auto", padding: "2rem", display: "flex", flexDirection: "column", gap: "1.75rem" }}
    >
      {messages.length === 0 && !isStreaming && (
        <div style={{ margin: "auto", textAlign: "center", maxWidth: 420 }}>
          <h2 className="t-xl" style={{ color: "#fff", marginBottom: "0.5rem" }}>How can I help?</h2>
          <p className="t-sm">
            Ask about alignment, timelines, decision history, or generate a presentation or scorecard.
          </p>
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && (
        <div style={{ display: "flex", gap: "0.85rem", alignSelf: "flex-start", maxWidth: "85%", alignItems: "flex-start" }}>
          <AssistantAvatar />
          <div style={{ fontSize: "0.95rem", color: "var(--foreground)", lineHeight: 1.6 }}>
            {streamText ? <Markdown text={streamText} /> : <span className="t-sm">Assistant is thinking...</span>}
          </div>
        </div>
      )}
    </div>
  );
}
