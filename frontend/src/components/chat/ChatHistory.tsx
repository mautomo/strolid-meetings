"use client";

import { useState } from "react";
import { Search, Plus, Share2, Trash2, X, Check, Users } from "lucide-react";
import { useChat } from "@/context/ChatContext";
import { shareConversation, unshareConversation, deleteConversation } from "@/lib/api";
import type { Conversation } from "@/lib/types";

export function ChatHistory() {
  const { conversations, activeConversationId, selectConversation, newChat, refreshConversations, user } = useChat();
  const [filter, setFilter] = useState("");
  const [shareFor, setShareFor] = useState<string | null>(null);
  const [shareEmail, setShareEmail] = useState("");
  const [error, setError] = useState("");

  const visible = conversations.filter((c) => c.title.toLowerCase().includes(filter.toLowerCase()));

  const withToken = async (fn: (token: string) => Promise<void>) => {
    if (!user) return;
    setError("");
    try {
      await fn(await user.getIdToken());
      await refreshConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", height: "100%", minHeight: 0 }}>
      <button type="button" className="btn btn-primary btn-sm" style={{ gap: "0.4rem" }} onClick={() => void newChat()}>
        <Plus size={15} /> New chat
      </button>

      <div style={{ position: "relative" }}>
        <Search size={15} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--mid-gray)" }} />
        <input type="text" placeholder="Search conversations" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "100%", paddingLeft: "2rem", fontSize: "0.85rem" }} />
      </div>

      {error && <p style={{ color: "var(--destructive)", fontSize: "0.8rem" }}>{error}</p>}

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        {visible.length === 0 && <p className="t-sm" style={{ padding: "0.5rem" }}>No conversations yet.</p>}
        {visible.map((c) => (
          <ConversationRow
            key={c.id}
            conv={c}
            active={c.id === activeConversationId}
            onSelect={() => selectConversation(c.id)}
            onShareToggle={() => {
              setShareFor(shareFor === c.id ? null : c.id);
              setShareEmail("");
            }}
            shareOpen={shareFor === c.id}
            onDelete={() => void withToken((t) => deleteConversation(t, c.id))}
            onAddShare={() =>
              void withToken(async (t) => {
                await shareConversation(t, c.id, shareEmail.trim().toLowerCase());
                setShareEmail("");
              })
            }
            onRemoveShare={(email) => void withToken((t) => unshareConversation(t, c.id, email))}
            shareEmail={shareEmail}
            setShareEmail={setShareEmail}
          />
        ))}
      </div>
    </div>
  );
}

function ConversationRow({
  conv,
  active,
  onSelect,
  onShareToggle,
  shareOpen,
  onDelete,
  onAddShare,
  onRemoveShare,
  shareEmail,
  setShareEmail,
}: {
  conv: Conversation;
  active: boolean;
  onSelect: () => void;
  onShareToggle: () => void;
  shareOpen: boolean;
  onDelete: () => void;
  onAddShare: () => void;
  onRemoveShare: (email: string) => void;
  shareEmail: string;
  setShareEmail: (v: string) => void;
}) {
  return (
    <div style={{ background: active ? "var(--surface-2)" : "var(--surface-1)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-base)" }} className={active ? "active-bar" : undefined}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.55rem 0.65rem" }}>
        <button type="button" onClick={onSelect} style={{ flex: 1, minWidth: 0, textAlign: "left", background: "transparent", display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#fff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{conv.title}</span>
          <span className="t-xs" style={{ letterSpacing: "0.03em" }}>
            {conv.isOwner
              ? conv.sharedWith.length > 0
                ? `shared with ${conv.sharedWith.length}`
                : "private"
              : `shared by ${conv.ownerEmail ?? "owner"}`}
          </span>
        </button>
        {conv.isOwner ? (
          <>
            <button type="button" className="btn-ghost" aria-label="Share" title="Share" onClick={onShareToggle} style={{ padding: 5, color: shareOpen ? "var(--star)" : "var(--muted-foreground)" }}>
              <Share2 size={15} />
            </button>
            <button type="button" className="btn-ghost" aria-label="Delete" title="Delete" onClick={onDelete} style={{ padding: 5, color: "var(--muted-foreground)" }}>
              <Trash2 size={15} />
            </button>
          </>
        ) : (
          <Users size={14} color="var(--mid-gray)" />
        )}
      </div>

      {shareOpen && conv.isOwner && (
        <div style={{ padding: "0 0.65rem 0.6rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <input type="email" placeholder="email to share (read-only)" value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} style={{ flex: 1, fontSize: "0.8rem", padding: "6px 8px" }} />
            <button type="button" className="btn btn-secondary btn-sm" aria-label="Add share" onClick={onAddShare} disabled={!shareEmail.trim()}>
              <Check size={15} />
            </button>
          </div>
          {conv.sharedWith.map((email) => (
            <div key={email} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.78rem", color: "var(--muted-foreground)" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{email}</span>
              <button type="button" className="btn-ghost" aria-label={`Unshare ${email}`} onClick={() => onRemoveShare(email)} style={{ padding: 3 }}>
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
