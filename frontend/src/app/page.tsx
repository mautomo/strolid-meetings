"use client";

import { ChatProvider, useChat } from "@/context/ChatContext";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { AppShell } from "@/components/shell/AppShell";

function AppRoot() {
  const { user, authLoading } = useChat();

  if (authLoading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <p className="t-sm" style={{ color: "var(--star)", fontSize: "1rem" }}>Loading Strolid Platform...</p>
      </div>
    );
  }

  if (!user) return <LoginScreen />;
  return <AppShell />;
}

export default function Home() {
  return (
    <ChatProvider>
      <AppRoot />
    </ChatProvider>
  );
}
