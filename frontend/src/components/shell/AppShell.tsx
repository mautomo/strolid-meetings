"use client";

import { FloatingSidebar } from "./FloatingSidebar";
import { SidePanel } from "./SidePanel";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { Canvas } from "@/components/canvas/Canvas";

export function AppShell() {
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--background)" }}>
      <FloatingSidebar />
      <SidePanel />
      <ChatWindow />
      <Canvas />
    </div>
  );
}
