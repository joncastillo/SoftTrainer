// The live session: voice loop, camera, transcript, subtitles, timer.

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { startMic, type MicHandle } from "../audio/mic";
import { CameraPanel } from "../components/CameraPanel";
import { Markdown } from "../components/Markdown";
import { ReportView } from "../components/ReportView";
import { useSessionSocket } from "../hooks/useSessionSocket";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function SessionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const socket = useSessionSocket(id);
  const [subtitlesOn, setSubtitlesOn] = useState(true);
  const [micOn, setMicOn] = useState(false);
  const [draft, setDraft] = useState("");
  const [clock, setClock] = useState<number | null>(null);
  const micRef = useRef<MicHandle | null>(null);
  const recognitionRef = useRef<any>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getSession(id).then((s) => setSubtitlesOn(s.meta.subtitles ?? true)).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (socket.secondsLeft == null) return;
    setClock(socket.secondsLeft);
    const t = setInterval(() => setClock((c) => (c != null && c > 0 ? c - 1 : c)), 1000);
    return () => clearInterval(t);
  }, [socket.secondsLeft]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [socket.messages, socket.partial]);

  const stopMic = useCallback(() => {
    micRef.current?.stop();
    micRef.current = null;
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setMicOn(false);
  }, []);

  const toggleMic = useCallback(async () => {
    if (micOn) {
      stopMic();
      return;
    }
    if (socket.serverSpeech?.stt_available) {
      micRef.current = await startMic(socket.sendAudio, socket.endUtterance);
    } else {
      // No Kyutai models on the server, use the browser recognizer.
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SR) {
        alert("Speech input needs Kyutai models on the server or a Chromium based browser.");
        return;
      }
      const rec = new SR();
      rec.continuous = true;
      rec.interimResults = false;
      rec.onresult = (e: any) => {
        const text = e.results[e.results.length - 1][0].transcript;
        if (text.trim()) socket.sendText(text.trim());
      };
      rec.start();
      recognitionRef.current = rec;
    }
    setMicOn(true);
  }, [micOn, socket, stopMic]);

  useEffect(() => stopMic, [stopMic]);

  useEffect(() => {
    if (socket.ended) stopMic();
  }, [socket.ended, stopMic]);

  const submitDraft = () => {
    if (draft.trim()) {
      socket.sendText(draft.trim());
      setDraft("");
    }
  };

  if (socket.report) {
    return (
      <div className="page">
        <ReportView report={socket.report} />
        <button className="primary" onClick={() => navigate("/")}>New session</button>
      </div>
    );
  }

  return (
    <div className="page session">
      <header className="session-bar">
        <div className={`timer ${clock != null && clock < 120 ? "warning" : ""}`}>
          {clock != null ? formatTime(clock) : "--:--"}
        </div>
        <div className="session-status">
          {!socket.connected && <span className="error">disconnected</span>}
          {socket.speaking && <span className="speaking">trainer speaking</span>}
          {socket.generatingReport && <span>preparing your report...</span>}
        </div>
        <div className="session-actions">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={subtitlesOn}
              onChange={(e) => setSubtitlesOn(e.target.checked)}
            />
            Subtitles
          </label>
          <button className="danger" onClick={socket.endSession} disabled={socket.ended}>
            End session
          </button>
        </div>
      </header>

      <div className="session-body">
        <div className="conversation" ref={logRef}>
          {socket.messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.role === "assistant" ? <Markdown text={m.text} /> : m.text}
            </div>
          ))}
          {socket.partial && <div className="bubble user partial">{socket.partial}</div>}
        </div>

        <aside className="side-panel">
          <CameraPanel onFrame={socket.sendFrame} rolling={socket.rolling} />
          <div className="mic-controls">
            <button className={micOn ? "danger" : "primary"} onClick={toggleMic} disabled={socket.ended}>
              {micOn ? "Mute microphone" : "Enable microphone"}
            </button>
          </div>
          <div className="text-input">
            <textarea
              rows={2}
              value={draft}
              placeholder="Or type your reply..."
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitDraft();
                }
              }}
            />
            <button onClick={submitDraft} disabled={socket.ended}>Send</button>
          </div>
        </aside>
      </div>

      {subtitlesOn && socket.subtitle && (
        <div className="subtitles">{socket.subtitle}</div>
      )}
      {socket.error && <div className="error banner">{socket.error}</div>}
    </div>
  );
}
