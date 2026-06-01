"use client";

import { X } from "lucide-react";
import { useChat, type SidebarPanel } from "@/context/ChatContext";
import { ScopePanel } from "./ScopePanel";
import { ChatHistory } from "@/components/chat/ChatHistory";
import { AdminPanel } from "@/components/admin/AdminPanel";

const TITLES: Record<Exclude<SidebarPanel, null>, string> = {
  history: "Chat history",
  scope: "Scope and filters",
  admin: "Admin",
  settings: "Settings",
};

export function SidePanel() {
  const { activePanel, setActivePanel } = useChat();
  if (!activePanel) return null;

  return (
    <aside
      style={{
        width: 320,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        margin: "0.75rem 0",
        padding: "1rem",
        background: "var(--surface-1)",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-panel)",
        boxShadow: "var(--shadow-2)",
        minHeight: 0,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 className="t-l" style={{ color: "#fff" }}>{TITLES[activePanel]}</h2>
        <button type="button" className="btn-ghost" aria-label="Close panel" onClick={() => setActivePanel(null)} style={{ padding: 6, borderRadius: "var(--radius-base)" }}>
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        {activePanel === "scope" && <ScopePanel />}
        {activePanel === "history" && <ChatHistory />}
        {activePanel === "admin" && <AdminPanel />}
        {activePanel === "settings" && <p className="t-sm">This area arrives in a later phase.</p>}
      </div>
    </aside>
  );
}
