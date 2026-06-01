import type { ScorecardArtifact as ScorecardData } from "@/lib/types";

export function ScorecardArtifact({ data }: { data: ScorecardData }) {
  const cells: { label: string; value: number; color: string }[] = [
    { label: "Completed", value: data.stats.completed, color: "var(--emerald)" },
    { label: "Open", value: data.stats.open, color: "var(--star)" },
    { label: "Delayed", value: data.stats.delayed, color: "var(--amber)" },
    { label: "Abandoned", value: data.stats.abandoned, color: "var(--destructive)" },
  ];

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card-premium" style={{ textAlign: "center" }}>
        <div className="t-xs">Reliability score</div>
        <div className="font-mono" style={{ fontSize: "3rem", fontWeight: 600, color: "var(--star)", lineHeight: 1 }}>
          {data.reliability.toFixed(1)}%
        </div>
        <div style={{ width: "100%", height: 8, background: "var(--viz-track)", borderRadius: "var(--radius-pill)", marginTop: "1rem", overflow: "hidden" }}>
          <div style={{ width: `${data.reliability}%`, height: "100%", background: "var(--star)" }} />
        </div>
        <div className="t-sm" style={{ marginTop: "0.5rem" }}>Calculated from action item completion rate</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
        {cells.map((c) => (
          <div key={c.label} className="card">
            <div className="t-xs">{c.label}</div>
            <div className="font-mono" style={{ fontSize: "1.5rem", fontWeight: 600, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {data.top_topics && data.top_topics.length > 0 && (
        <div className="card">
          <h4 className="t-xs" style={{ marginBottom: "0.75rem" }}>Key areas of focus</h4>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {data.top_topics.map((t, i) => (
              <span key={i} className="badge badge-signal">{t}</span>
            ))}
          </div>
        </div>
      )}

      {data.key_insights && data.key_insights.length > 0 && (
        <div className="card">
          <h4 className="t-xs" style={{ marginBottom: "0.75rem" }}>Qualitative insights</h4>
          <ul style={{ paddingLeft: "1.2rem", color: "var(--muted-foreground)", fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {data.key_insights.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
