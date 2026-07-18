// Stylized talking-head for the trainer, lip-synced to TTS playback.
//
// The mouth is driven by the live playback loudness from AudioQueue's
// analyser; when the browser-voice fallback is speaking (no analyser
// signal available) a gentle synthetic flutter stands in. Everything is
// mutated directly on SVG nodes inside one requestAnimationFrame loop so
// React never re-renders at animation rate.

import { useEffect, useRef } from "react";

interface Props {
  getLevel: () => number;
  speaking: boolean;
}

export function TrainerAvatar({ getLevel, speaking }: Props) {
  const mouthRef = useRef<SVGEllipseElement>(null);
  const eyesRef = useRef<SVGGElement>(null);
  const headRef = useRef<SVGGElement>(null);
  const speakingRef = useRef(speaking);
  speakingRef.current = speaking;

  useEffect(() => {
    let raf = 0;
    let mouth = 0;           // smoothed mouth openness 0..1
    let nextBlink = performance.now() + 2000 + Math.random() * 3000;
    let blinkUntil = 0;
    let phase = 0;           // drives idle bob and the fallback flutter

    const tick = (now: number) => {
      phase += 0.03;
      let target = getLevel();
      if (target === 0 && speakingRef.current) {
        // Browser-voice fallback: no analyser to read, fake a cadence.
        target = 0.25 + 0.2 * Math.abs(Math.sin(phase * 4)) * Math.abs(Math.sin(phase * 1.7));
      }
      // Fast attack, slower decay reads as natural articulation.
      mouth = target > mouth ? mouth + (target - mouth) * 0.6 : mouth + (target - mouth) * 0.25;

      if (mouthRef.current) {
        mouthRef.current.setAttribute("ry", (1.5 + mouth * 9).toFixed(2));
        mouthRef.current.setAttribute("rx", (10 - mouth * 2.5).toFixed(2));
      }
      if (now > nextBlink) {
        blinkUntil = now + 130;
        nextBlink = now + 2000 + Math.random() * 3500;
      }
      if (eyesRef.current) {
        eyesRef.current.setAttribute(
          "transform", `scale(1 ${now < blinkUntil ? 0.12 : 1})`);
      }
      if (headRef.current) {
        const bob = Math.sin(phase) * 1.2 + (speakingRef.current ? Math.sin(phase * 3.1) * 0.8 : 0);
        headRef.current.setAttribute("transform", `translate(0 ${bob.toFixed(2)})`);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [getLevel]);

  return (
    <div className={`trainer-avatar ${speaking ? "speaking" : ""}`}>
      <svg viewBox="0 0 120 120" role="img" aria-label="Trainer">
        {/* shoulders */}
        <path d="M18 120 Q18 92 60 92 Q102 92 102 120 Z" fill="#2b3550" />
        <g ref={headRef}>
          {/* head */}
          <ellipse cx="60" cy="52" rx="30" ry="34" fill="#c9a184" />
          {/* hair */}
          <path d="M30 46 Q30 16 60 16 Q90 16 90 46 Q84 30 60 28 Q36 30 30 46 Z" fill="#3a2e28" />
          {/* eyes: transform-origin at eye line so blinks close in place */}
          <g style={{ transformOrigin: "60px 48px" }}>
            <g ref={eyesRef} style={{ transformOrigin: "60px 48px" }}>
              <ellipse cx="48" cy="48" rx="4" ry="4.5" fill="#22262e" />
              <ellipse cx="72" cy="48" rx="4" ry="4.5" fill="#22262e" />
            </g>
          </g>
          {/* brows */}
          <path d="M42 40 Q48 37 54 40" stroke="#3a2e28" strokeWidth="2" fill="none" strokeLinecap="round" />
          <path d="M66 40 Q72 37 78 40" stroke="#3a2e28" strokeWidth="2" fill="none" strokeLinecap="round" />
          {/* nose */}
          <path d="M60 52 Q62 60 58 62" stroke="#a97f62" strokeWidth="2" fill="none" strokeLinecap="round" />
          {/* mouth */}
          <ellipse ref={mouthRef} cx="60" cy="73" rx="10" ry="1.5" fill="#5e3438" />
        </g>
      </svg>
    </div>
  );
}
