import type { TimelineArtifact as TimelineData } from "@/lib/types";

const DOT: Record<string, string> = {
  decision: "var(--emerald)",
  action_item: "var(--star)",
  document: "var(--amber)",
};

export function TimelineArtifact({ data }: { data: TimelineData }) {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.25rem", position: "relative", paddingLeft: "1.5rem" }}>
      <div style={{ position: "absolute", left: 4, top: 8, bottom: 8, width: 2, background: "var(--hairline)" }} />
      {data.events.map((evt) => (
        <div key={evt.id} style={{ position: "relative" }}>
          <div style={{ position: "absolute", left: -23, top: 6, width: 10, height: 10, borderRadius: "50%", background: DOT[evt.type] || "var(--star)" }} />
          <div className="card">
            <div className="font-mono" style={{ fontSize: "0.72rem", color: "var(--star)", marginBottom: "0.25rem", letterSpacing: "0.06em" }}>
              {evt.date}
            </div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "#fff", marginBottom: "0.25rem" }}>{evt.summary}</div>
            {evt.details && <div className="t-sm">{evt.details}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
