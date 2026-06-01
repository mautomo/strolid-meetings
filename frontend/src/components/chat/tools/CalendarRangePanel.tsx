"use client";

import { useState } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import "react-day-picker/style.css";
import { useChat } from "@/context/ChatContext";

function fmt(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function parse(s: string): Date | undefined {
  if (!s) return undefined;
  const [y, m, d] = s.split("-").map(Number);
  return y && m && d ? new Date(y, m - 1, d) : undefined;
}

export function CalendarRangePanel({ onDone }: { onDone: () => void }) {
  const { startDate, endDate, setStartDate, setEndDate } = useChat();
  const [range, setRange] = useState<DateRange | undefined>({
    from: parse(startDate),
    to: parse(endDate),
  });

  const apply = (r: DateRange | undefined) => {
    setRange(r);
    setStartDate(r?.from ? fmt(r.from) : "");
    setEndDate(r?.to ? fmt(r.to) : "");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <style>{`
        .rdp-root { --rdp-accent-color: var(--star); --rdp-accent-background-color: rgba(0,238,255,0.12); --rdp-today-color: var(--star); margin: 0; font-size: 0.8rem; }
        .rdp-day_button { color: var(--foreground); }
        .rdp-chevron { fill: var(--muted-foreground); }
      `}</style>
      <DayPicker mode="range" selected={range} onSelect={apply} numberOfMonths={1} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", color: "var(--star)", padding: "2px 4px" }} onClick={() => apply(undefined)}>
          Clear
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}
