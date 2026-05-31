"use client";

import { useChat } from "@/context/ChatContext";

export function ScopePanel() {
  const {
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    selectedMeetingIds,
    setSelectedMeetingIds,
    meetings,
    stats,
  } = useChat();

  const toggleMeeting = (id: string) => {
    if (selectedMeetingIds.includes(id)) {
      setSelectedMeetingIds(selectedMeetingIds.filter((m) => m !== id));
    } else {
      setSelectedMeetingIds([...selectedMeetingIds, id]);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", height: "100%", minHeight: 0 }}>
      <p className="t-sm">Filters apply to this conversation. With no meetings checked, all meetings are in scope.</p>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <label className="t-xs">Date range</label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={{ width: "50%", fontSize: "0.8rem" }} />
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={{ width: "50%", fontSize: "0.8rem" }} />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", flex: 1, minHeight: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label className="t-xs">Meetings</label>
          <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.7rem" }}>
            <button type="button" className="btn-ghost" style={{ color: "var(--star)", padding: "2px 4px", fontSize: "0.7rem" }} onClick={() => setSelectedMeetingIds(meetings.map((m) => m.meeting_id))}>
              All
            </button>
            <button type="button" className="btn-ghost" style={{ color: "var(--star)", padding: "2px 4px", fontSize: "0.7rem" }} onClick={() => setSelectedMeetingIds([])}>
              None
            </button>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", background: "var(--surface-1)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-base)", padding: "0.4rem" }}>
          {meetings.map((m) => {
            const checked = selectedMeetingIds.includes(m.meeting_id);
            return (
              <label
                key={m.meeting_id}
                title={m.title || m.meeting_id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.35rem 0.5rem",
                  borderRadius: "var(--radius-pill)",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  color: checked ? "#fff" : "var(--muted-foreground)",
                }}
              >
                <input type="checkbox" checked={checked} onChange={() => toggleMeeting(m.meeting_id)} style={{ width: 14, height: 14, accentColor: "var(--star)", padding: 0 }} />
                <span style={{ textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
                  {m.date} - {m.title || m.meeting_id}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <Stat label="Meetings" value={stats.meetings_count} />
        <Stat label="Decisions" value={stats.decisions_count} accent />
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="card" style={{ flex: 1, padding: "0.75rem 1rem" }}>
      <div className="t-xs">{label}</div>
      <div className="font-mono" style={{ fontSize: "1.3rem", fontWeight: 600, color: accent ? "var(--star)" : "#fff" }}>
        {value}
      </div>
    </div>
  );
}
