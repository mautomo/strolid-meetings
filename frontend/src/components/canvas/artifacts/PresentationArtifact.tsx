"use client";

import { useChat } from "@/context/ChatContext";
import type { PresentationArtifact as PresentationData } from "@/lib/types";

export function PresentationArtifact({ data }: { data: PresentationData }) {
  const { slideIndex, setSlideIndex } = useChat();
  const slide = data.slides[slideIndex];
  if (!slide) return null;

  return (
    <div className="animate-fade-in" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div className="card-glass" style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", minHeight: 300 }}>
        <h3 className="t-xl" style={{ color: "#fff", marginBottom: "0.75rem" }}>{slide.title}</h3>
        {slide.subtitle && (
          <h4 style={{ fontSize: "0.9rem", color: "var(--star)", marginBottom: "1.25rem", fontWeight: 600 }}>{slide.subtitle}</h4>
        )}
        {slide.bullets && slide.bullets.length > 0 ? (
          <ul style={{ display: "flex", flexDirection: "column", gap: "0.6rem", paddingLeft: "1.2rem", color: "var(--muted-foreground)", fontSize: "0.9rem" }}>
            {slide.bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        ) : (
          <p style={{ color: "var(--muted-foreground)", fontSize: "0.95rem" }}>{slide.content}</p>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1.25rem" }}>
        <button type="button" className="btn btn-secondary btn-sm" disabled={slideIndex === 0} onClick={() => setSlideIndex(slideIndex - 1)}>
          Prev
        </button>
        <span className="font-mono t-xs">
          {slideIndex + 1} / {data.slides.length}
        </span>
        <button type="button" className="btn btn-secondary btn-sm" disabled={slideIndex === data.slides.length - 1} onClick={() => setSlideIndex(slideIndex + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
