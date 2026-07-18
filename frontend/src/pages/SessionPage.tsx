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
  const [micError, setMicError] = useState("");
  const [browserPartial, setBrowserPartial] = useState("");
  const [draft, setDraft] = useState("");
  const [clock, setClock] = useState<number | null>(null);
  const micRef = useRef<MicHandle | null>(null);
  const recognitionRef = useRef<any>(null);
  const listeningRef = useRef(false);
  const trainerSpeakingRef = useRef(false);
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
    listeningRef.current = false;
    micRef.current?.stop();
    micRef.current = null;
    try {
      recognitionRef.current?.stop();
    } catch {
      /* already stopped */
    }
    recognitionRef.current = null;
    setBrowserPartial("");
    setMicOn(false);
  }, []);

  const startBrowserRecognition = useCallback((): boolean => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setMicError(
        "This browser has no speech recognition. Use Chrome or Edge, install the " +
          "server speech models, or type your replies below.",
      );
      return false;
    }
    const rec = new SR();
    rec.lang = navigator.language || "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        if (result.isFinal) {
          const text = result[0].transcript.trim();
          if (text) socket.sendText(text);
          setBrowserPartial("");
        } else {
          interim += result[0].transcript;
        }
      }
      if (interim) setBrowserPartial(interim);
    };
    rec.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      const hints: Record<string, string> = {
        "not-allowed": "Microphone permission was denied. Allow it in the address bar and try again.",
        network: "The browser recognizer needs an internet connection.",
        "audio-capture": "No microphone was found. Check your input device.",
      };
      setMicError(hints[e.error] ?? `Microphone error: ${e.error}`);
    };
    // Chrome stops listening after pauses, restart while the mic is on
    // but stay quiet while the trainer is speaking to avoid echo.
    rec.onend = () => {
      setBrowserPartial("");
      if (listeningRef.current && !trainerSpeakingRef.current) {
        try {
          rec.start();
        } catch {
          /* restarting too fast, the next onend retries */
        }
      }
    };
    recognitionRef.current = rec;
    try {
      rec.start();
    } catch {
      /* already started */
    }
    return true;
  }, [socket]);

  const toggleMic = useCallback(async () => {
    setMicError("");
    if (micOn) {
      stopMic();
      return;
    }
    if (socket.serverSpeech?.stt_available) {
      try {
        micRef.current = await startMic(socket.sendAudio, socket.endUtterance);
      } catch {
        setMicError("Microphone access was denied or no input device was found.");
        return;
      }
    } else if (!startBrowserRecognition()) {
      return;
    }
    listeningRef.current = true;
    setMicOn(true);
  }, [micOn, socket, stopMic, startBrowserRecognition]);

  useEffect(() => stopMic, [stopMic]);

  useEffect(() => {
    if (socket.ended) stopMic();
  }, [socket.ended, stopMic]);

  useEffect(() => {
    trainerSpeakingRef.current = socket.speaking;
    const rec = recognitionRef.current;
    if (!rec || !listeningRef.current) return;
    if (socket.speaking) {
      try {
        rec.stop();
      } catch {
        /* already stopped */
      }
    } else {
      try {
        rec.start();
      } catch {
        /* already running */
      }
    }
  }, [socket.speaking]);

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
          {micOn && !socket.speaking && <span className="speaking">listening</span>}
          {socket.generatingReport && <span>preparing your report...</span>}
          {socket.serverSpeech && (
            <span className="tag" title={socket.serverSpeech.tts_detail ?? ""}>
              voice: {socket.serverSpeech.tts_engine ?? "browser"}
            </span>
          )}
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
          {browserPartial && <div className="bubble user partial">{browserPartial}</div>}
        </div>

        <aside className="side-panel">
          <CameraPanel onFrame={socket.sendFrame} rolling={socket.rolling} tip={socket.coachTip} />
          <div className="mic-controls">
            <button className={micOn ? "danger" : "primary"} onClick={toggleMic} disabled={socket.ended}>
              {micOn ? "Mute microphone" : "Enable microphone"}
            </button>
            {micError && <p className="error">{micError}</p>}
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
