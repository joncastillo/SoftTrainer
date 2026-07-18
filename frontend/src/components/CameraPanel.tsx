// Webcam preview that periodically ships frames to the backend.

import { useEffect, useRef, useState } from "react";
import type { BehaviorSummary, CoachTip } from "../types";

interface Props {
  onFrame: (jpegB64: string) => void;
  rolling: BehaviorSummary | null;
  tip?: CoachTip | null;
  intervalMs?: number;
}

export function CameraPanel({ onFrame, rolling, tip, intervalMs = 700 }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [shownTip, setShownTip] = useState<CoachTip | null>(null);

  // Surface each new coaching tip briefly, then let it fade on its own so
  // it never lingers or stacks up over the camera preview.
  useEffect(() => {
    if (!tip) return;
    setShownTip(tip);
    const t = window.setTimeout(() => setShownTip(null), 6000);
    return () => clearTimeout(t);
  }, [tip]);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let timer: number | null = null;

    navigator.mediaDevices
      .getUserMedia({ video: { width: 640, height: 480 } })
      .then((s) => {
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        timer = window.setInterval(() => {
          const video = videoRef.current;
          const canvas = canvasRef.current;
          if (!video || !canvas || video.readyState < 2) return;
          canvas.width = 320;
          canvas.height = 240;
          const ctx = canvas.getContext("2d");
          if (!ctx) return;
          ctx.drawImage(video, 0, 0, 320, 240);
          onFrame(canvas.toDataURL("image/jpeg", 0.6));
        }, intervalMs);
      })
      .catch(() => {
        /* camera denied, behavior analysis just stays off */
      });

    return () => {
      if (timer) clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onFrame, intervalMs]);

  return (
    <div className="camera-panel">
      <video ref={videoRef} autoPlay muted playsInline />
      <canvas ref={canvasRef} style={{ display: "none" }} />
      {shownTip && (
        <div className={`camera-coach-tip ${shownTip.tone ?? "nudge"}`} role="status">
          {shownTip.text}
        </div>
      )}
      {rolling?.available && (
        <div className="camera-stats">
          <span>Eye contact {rolling.eye_contact_pct ?? 0}%</span>
          <span>Confidence {rolling.confidence_score ?? 0}</span>
        </div>
      )}
    </div>
  );
}
