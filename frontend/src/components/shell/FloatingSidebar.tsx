"use client";

import {
  MessageSquarePlus,
  History,
  SlidersHorizontal,
  Shield,
  Settings,
  LogOut,
} from "lucide-react";
import { useChat, type SidebarPanel } from "@/context/ChatContext";

const RAIL_WIDTH = 62;

export function FloatingSidebar() {
  const { activePanel, setActivePanel, newChat, signOutUser, currentRole } = useChat();

  const toggle = (panel: Exclude<SidebarPanel, null>) =>
    setActivePanel(activePanel === panel ? null : panel);

  return (
    <nav
      aria-label="Primary"
      style={{
        width: RAIL_WIDTH,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.75rem 0",
        margin: "0.75rem 0 0.75rem 0.75rem",
        background: "var(--surface-1)",
        border: "1px solid var(--hairline)",
        borderRadius: "var(--radius-panel)",
        boxShadow: "var(--shadow-2)",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/images/brand/vandoko-v2-icon-white.png"
        alt="Vandoko"
        style={{ width: 28, height: 28, marginBottom: "0.5rem" }}
      />

      <RailButton label="New chat" active={false} onClick={() => void newChat()}>
        <MessageSquarePlus size={20} />
      </RailButton>
      <RailButton label="Chat history" active={activePanel === "history"} onClick={() => toggle("history")}>
        <History size={20} />
      </RailButton>
      <RailButton label="Scope and filters" active={activePanel === "scope"} onClick={() => toggle("scope")}>
        <SlidersHorizontal size={20} />
      </RailButton>
      {currentRole === "admin" && (
        <RailButton label="Admin" active={activePanel === "admin"} onClick={() => toggle("admin")}>
          <Shield size={20} />
        </RailButton>
      )}

      <div style={{ flex: 1 }} />

      <RailButton label="Settings" active={activePanel === "settings"} onClick={() => toggle("settings")}>
        <Settings size={20} />
      </RailButton>
      <RailButton label="Log out" active={false} onClick={() => void signOutUser()}>
        <LogOut size={20} />
      </RailButton>
    </nav>
  );
}

function RailButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={active ? "active-bar" : undefined}
      style={{
        width: 40,
        height: 40,
        borderRadius: "var(--radius-base)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: active ? "var(--surface-3)" : "transparent",
        color: active ? "var(--star)" : "var(--muted-foreground)",
      }}
    >
      {children}
    </button>
  );
}
