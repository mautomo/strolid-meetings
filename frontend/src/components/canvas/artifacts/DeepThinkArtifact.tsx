import { ArrowDown, User } from "lucide-react";
import type { DeepThinkArtifact as DeepThinkData, DeepThinkReversal } from "@/lib/types";

// firm = committed, tentative = soft, exploratory = open. Semantic colors per brand.
const CONFIDENCE_COLOR: Record<string, string> = {
  firm: "var(--emerald)",
  tentative: "var(--amber)",
  exploratory: "var(--muted-foreground)",
};

export function DeepThinkArtifact({ data }: { data: DeepThinkData }) {
  if (!data.reversals || data.reversals.length === 0) {
    return (
      <div className="card t-sm animate-fade-in">
        No per-person direction reversals found for this scope.
      </div>
    );
  }

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {data.reversals.map((r) => (
        <ReversalCard key={r.id} r={r} />
      ))}
    </div>
  );
}

function ReversalCard({ r }: { r: DeepThinkReversal }) {
  return (
    <div className="card-premium" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <User size={16} color="var(--star)" />
          <span style={{ fontSize: "0.95rem", fontWeight: 600, color: "#fff" }}>{r.person}</span>
        </div>
        <span className="badge badge-default">{r.topic}</span>
      </div>

      <PositionRow
        label="Set direction"
        date={r.original_date}
        meeting={r.original_meeting}
        position={r.original_position}
        confidence={r.original_confidence}
      />

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", paddingLeft: "0.1rem" }}>
        <ArrowDown size={16} color="var(--amber)" />
        <span className="font-mono t-xs" style={{ color: "var(--amber)", letterSpacing: "0.06em" }}>
          {r.days_between} days later
        </span>
      </div>

      <PositionRow
        label="Reversed to"
        date={r.change_date}
        meeting={r.change_meeting}
        position={r.new_position}
        confidence={r.new_confidence}
      />
    </div>
  );
}

function PositionRow({
  label,
  date,
  meeting,
  position,
  confidence,
}: {
  label: string;
  date: string;
  meeting: string;
  position: string;
  confidence: string;
}) {
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="t-xs" style={{ letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</span>
        <span className="font-mono t-xs" style={{ color: "var(--star)", letterSpacing: "0.06em" }}>{date}</span>
      </div>
      <div style={{ fontSize: "0.88rem", color: "#fff" }}>{position}</div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: CONFIDENCE_COLOR[confidence] || "var(--muted-foreground)",
          }}
        />
        <span className="t-xs" style={{ letterSpacing: "0.04em" }}>{confidence}</span>
        <span className="t-xs" style={{ marginLeft: "auto" }}>{meeting}</span>
      </div>
    </div>
  );
}
