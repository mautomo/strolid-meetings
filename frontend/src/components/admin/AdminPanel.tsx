"use client";

import { useCallback, useEffect, useState } from "react";
import { UserPlus, Trash2, AlertCircle } from "lucide-react";
import { useChat } from "@/context/ChatContext";
import { fetchMembers, addMember, removeMember } from "@/lib/api";
import type { Member, Role } from "@/lib/types";

export function AdminPanel() {
  const { user, currentRole, allowlistEnforced } = useChat();
  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      const list = await fetchMembers(token);
      setMembers(list);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load members.");
    }
  }, [user]);

  // Inline async fetch (setState only in the async continuation) to satisfy the
  // set-state-in-effect rule; load() is reused by the invite/remove handlers.
  useEffect(() => {
    if (currentRole !== "admin" || !user) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const list = await fetchMembers(token);
        if (!cancelled) {
          setMembers(list);
          setError("");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load members.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentRole, user]);

  if (currentRole !== "admin") {
    return <p className="t-sm">Admin access required.</p>;
  }

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !email.trim()) return;
    setBusy(true);
    setError("");
    try {
      const token = await user.getIdToken();
      await addMember(token, email.trim(), role);
      setEmail("");
      setRole("user");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add member.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (target: string) => {
    if (!user) return;
    setError("");
    try {
      const token = await user.getIdToken();
      await removeMember(token, target);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member.");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", height: "100%", minHeight: 0 }}>
      {!allowlistEnforced && (
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", padding: "0.6rem 0.75rem", background: "rgba(210, 62, 8, 0.08)", border: "1px solid var(--amber)", borderRadius: "var(--radius-base)", color: "var(--amber)", fontSize: "0.78rem" }}>
          <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Allowlist is not enforced yet. Set ALLOWLIST_ENFORCED=true on the backend to gate access.</span>
        </div>
      )}

      <form onSubmit={invite} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <label className="t-xs">Invite member</label>
        <input type="email" placeholder="person@domain.com" value={email} onChange={(e) => setEmail(e.target.value)} style={{ fontSize: "0.85rem" }} />
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} style={{ flex: 1, fontSize: "0.85rem" }}>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !email.trim()} style={{ gap: "0.4rem" }}>
            <UserPlus size={15} /> Invite
          </button>
        </div>
      </form>

      {error && (
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", color: "var(--destructive)", fontSize: "0.8rem" }}>
          <AlertCircle size={15} /> {error}
        </div>
      )}

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        <label className="t-xs">Members ({members.length})</label>
        {members.length === 0 && <p className="t-sm">No members yet.</p>}
        {members.map((m) => (
          <div key={m.email} className="card" style={{ padding: "0.6rem 0.75rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: "0.82rem", color: "#fff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.email}</div>
              <div style={{ display: "flex", gap: "0.4rem", marginTop: 2 }}>
                <span className={m.role === "admin" ? "badge badge-signal" : "badge badge-outline"}>{m.role}</span>
                <span className="t-xs" style={{ letterSpacing: "0.04em" }}>{m.status}</span>
              </div>
            </div>
            <button type="button" className="btn-ghost" aria-label={`Remove ${m.email}`} onClick={() => remove(m.email)} style={{ padding: 6, color: "var(--muted-foreground)", flexShrink: 0 }}>
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
