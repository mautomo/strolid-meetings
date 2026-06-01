"use client";

import { useChat } from "@/context/ChatContext";
import { MessageList } from "./MessageList";
import { PromptBox } from "./PromptBox";

export function ChatWindow() {
  const { user } = useChat();
  const who = user?.phoneNumber || user?.email || "";

  return (
    <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, height: "100%", overflow: "hidden" }}>
      <header
        style={{
          padding: "1.1rem 2rem",
          borderBottom: "1px solid var(--hairline)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <h1 style={{ color: "#fff", fontSize: "1rem", fontWeight: 600 }}>Meeting Intelligence</h1>
          <span className="t-xs">ADK 2.0 conversational RAG</span>
        </div>
        <span className="t-sm" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>
          {who}
        </span>
      </header>

      <MessageList />
      <PromptBox />
    </main>
  );
}
