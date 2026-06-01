import type { ComparisonArtifact as ComparisonData } from "@/lib/types";

export function ComparisonArtifact({ data }: { data: ComparisonData }) {
  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card-premium">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="t-xs">Entity A</div>
            <div style={{ fontSize: "1rem", fontWeight: 600, color: "#fff" }}>{data.entity_a}</div>
          </div>
          <div
            style={{
              width: 80,
              height: 80,
              borderRadius: "50%",
              border: "2px solid var(--star)",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <div className="font-mono" style={{ fontSize: "1.25rem", fontWeight: 600, color: "#fff" }}>{data.alignment_score.toFixed(0)}%</div>
            <div className="t-xs" style={{ letterSpacing: "0.1em" }}>Align</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="t-xs">Entity B</div>
            <div style={{ fontSize: "1rem", fontWeight: 600, color: "#fff" }}>{data.entity_b}</div>
          </div>
        </div>
        <div className="t-sm" style={{ textAlign: "center", marginTop: "1rem" }}>
          Joint decisions: <strong style={{ color: "#fff" }}>{data.joint_decisions}</strong>
        </div>
      </div>

      {data.contrasting_viewpoints && data.contrasting_viewpoints.length > 0 && (
        <ListCard title="Contrasting viewpoints" items={data.contrasting_viewpoints} />
      )}
      {data.key_findings && data.key_findings.length > 0 && (
        <ListCard title="Strategic key findings" items={data.key_findings} />
      )}
    </div>
  );
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="card">
      <h4 className="t-xs" style={{ marginBottom: "0.75rem" }}>{title}</h4>
      <ul style={{ paddingLeft: "1.2rem", color: "var(--muted-foreground)", fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {items.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}
