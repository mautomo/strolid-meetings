import { Sparkles } from "lucide-react";

export function AssistantAvatar() {
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: "50%",
        background: "rgba(0, 238, 255, 0.08)",
        border: "1px solid rgba(0, 238, 255, 0.3)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <Sparkles size={16} color="var(--star)" strokeWidth={1.75} />
    </div>
  );
}

export function UserAvatar({ label = "U" }: { label?: string }) {
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: "50%",
        background: "var(--surface-3)",
        border: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "0.8rem",
        fontWeight: 600,
        color: "#fff",
        flexShrink: 0,
      }}
    >
      {label.slice(0, 1).toUpperCase()}
    </div>
  );
}
