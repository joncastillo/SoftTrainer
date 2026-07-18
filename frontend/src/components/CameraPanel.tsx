// Webcam preview that periodically ships frames to the backend.

import { useEffect, useRef } from "react";
import type { BehaviorSummary } from "../types";

interface Props {
  onFrame: (jpegB64: string) => void;
  rolling: BehaviorSummary | null;
  intervalMs?: number;
}

export function CameraPanel({ onFrame, rolling, intervalMs = 700 }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
      {rolling?.available && (
        <div className="camera-stats">
          <span>Eye contact {rolling.eye_contact_pct ?? 0}%</span>
          <span>Confidence {rolling.confidence_score ?? 0}</span>
        </div>
      )}
    </div>
  );
}
