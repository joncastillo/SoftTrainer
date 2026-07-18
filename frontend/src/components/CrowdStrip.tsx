// Scripted audience: a row of silhouettes that reacts to pressure events.

import { useEffect, useRef, useState } from "react";

const MEMBERS = 7;

interface Props {
  // Monotonic id per event so repeats retrigger the animation.
  event: { id: number; kind: string } | null;
}

export function CrowdStrip({ event }: Props) {
  const [active, setActive] = useState<{ index: number; kind: string } | null>(null);
  const lastId = useRef(0);

  useEffect(() => {
    if (!event || event.id === lastId.current) return;
    lastId.current = event.id;
    setActive({ index: Math.floor(Math.random() * MEMBERS), kind: event.kind });
    const t = window.setTimeout(() => setActive(null), 3000);
    return () => clearTimeout(t);
  }, [event]);

  return (
    <div className="crowd-strip" aria-hidden="true">
      {Array.from({ length: MEMBERS }, (_, i) => {
        const agitated = active?.index === i;
        return (
          <svg key={i} viewBox="0 0 40 30" className={agitated ? `agitated ${active.kind}` : ""}>
            <circle cx="20" cy="10" r="7" />
            <path d="M6 30 Q6 18 20 18 Q34 18 34 30 Z" />
            {agitated && active.kind === "heckle" && (
              // a raised arm for the heckler
              <path d="M31 16 Q37 10 36 3" fill="none" strokeWidth="3" className="arm" />
            )}
          </svg>
        );
      })}
    </div>
  );
}
