// The live session: voice loop, camera, transcript, subtitles, timer.

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { startMic, type MicHandle } from "../audio/mic";
import { Ambience } from "../audio/ambience";
import { CameraPanel } from "../components/CameraPanel";
import { CrowdStrip } from "../components/CrowdStrip";
import { ReflectionCard } from "../components/ReflectionCard";
import { TrainerAvatar } from "../components/TrainerAvatar";
import { Markdown } from "../components/Markdown";
import { ReportView } from "../components/ReportView";
import { useSessionSocket } from "../hooks/useSessionSocket";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const GROUNDING_SECONDS = 30;

// How long after the browser recognizer's last final result to wait before
// sending the collected turn. Mirrors SILENCE_END_MS in mic.ts: a pause to
// think must not hand the turn to the trainer.
const FLUSH_PAUSE_MS = 2800;

function GroundingOverlay({ onDone }: { onDone: () => void }) {
  const [left, setLeft] = useState(GROUNDING_SECONDS);
  useEffect(() => {
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (left <= 0) onDone();
  }, [left, onDone]);
  return (
    <div className="grounding-overlay">
      <div className="breath-circle" />
      <p>Breathe in as the circle grows, out as it shrinks.</p>
      <p className="hint">Starting in {Math.max(0, left)}s</p>
      <button className="link" onClick={onDone}>Skip</button>
    </div>
  );
}

export function SessionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  // "unknown" until meta loads, then either the breathing step or straight in.
  const [grounding, setGrounding] = useState<"unknown" | "active" | "done">("unknown");
  const socket = useSessionSocket(id, grounding === "done");
  const [subtitlesOn, setSubtitlesOn] = useState(true);
  const [pressureLevel, setPressureLevel] = useState("off");
  const [ambienceOn, setAmbienceOn] = useState(true);
  const ambienceRef = useRef<Ambience | null>(null);
  const [micOn, setMicOn] = useState(false);
  const [micError, setMicError] = useState("");
  const [browserPartial, setBrowserPartial] = useState("");
  const [draft, setDraft] = useState("");
  const [clock, setClock] = useState<number | null>(null);
  const micRef = useRef<MicHandle | null>(null);
  const recognitionRef = useRef<any>(null);
  // Browser recognition finalizes a result at every short pause; collect
  // finals here and only send once the user has actually stopped talking.
  const pendingFinalRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);
  const browserSpeakingRef = useRef(false);
  const listeningRef = useRef(false);
  const trainerSpeakingRef = useRef(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getSession(id)
      .then((s) => {
        setSubtitlesOn(s.meta.subtitles ?? true);
        setPressureLevel(s.meta.pressure ?? "off");
        setGrounding(s.meta.grounding && s.meta.status === "created" ? "active" : "done");
      })
      .catch(() => setGrounding("done"));
  }, [id]);

  // Room ambience runs for the whole live portion of a pressure session.
  useEffect(() => {
    if (grounding !== "done" || pressureLevel === "off" || socket.ended) return;
    const ambience = new Ambience();
    ambienceRef.current = ambience;
    ambience.start(pressureLevel);
    return () => {
      ambienceRef.current = null;
      ambience.stop();
    };
  }, [grounding, pressureLevel, socket.ended]);

  useEffect(() => {
    ambienceRef.current?.setMuted(!ambienceOn);
  }, [ambienceOn]);

  useEffect(() => {
    if (socket.secondsLeft == null) return;
    setClock(socket.secondsLeft);
    const t = setInterval(() => setClock((c) => (c != null && c > 0 ? c - 1 : c)), 1000);
    return () => clearInterval(t);
  }, [socket.secondsLeft]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [socket.messages, socket.partial]);

  const flushPending = useCallback(() => {
    if (flushTimerRef.current != null) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    const text = pendingFinalRef.current.trim();
    pendingFinalRef.current = "";
    setBrowserPartial("");
    if (text) socket.sendText(text);
    // Depend on the stable sendText callback, NOT the socket object: that
    // changes identity every state update, which would make stopMic unstable
    // and re-trigger its unmount-cleanup effect, killing the mic instantly.
  }, [socket.sendText]);

  const stopMic = useCallback(() => {
    listeningRef.current = false;
    flushPending();
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
  }, [flushPending]);

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
    // The server can only interrupt mid-sentence if it knows the user is
    // talking; browser recognition audio never reaches it, so report speech
    // activity transitions explicitly.
    const setSpeaking = (active: boolean) => {
      if (browserSpeakingRef.current !== active) {
        browserSpeakingRef.current = active;
        socket.sendSpeakingState(active);
      }
    };
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        if (result.isFinal) {
          const text = result[0].transcript.trim();
          setSpeaking(false);
          // Do not send yet: a final result only means a short pause. Hold
          // it and wait; if the user keeps going the pieces join into one turn.
          if (text) {
            pendingFinalRef.current =
              (pendingFinalRef.current + " " + text).trim();
          }
        } else {
          interim += result[0].transcript;
        }
      }
      if (interim) {
        setSpeaking(true);
        // Still talking: never flush mid-utterance.
        if (flushTimerRef.current != null) {
          clearTimeout(flushTimerRef.current);
          flushTimerRef.current = null;
        }
      } else if (pendingFinalRef.current) {
        if (flushTimerRef.current != null) clearTimeout(flushTimerRef.current);
        flushTimerRef.current = window.setTimeout(flushPending, FLUSH_PAUSE_MS);
      }
      setBrowserPartial((pendingFinalRef.current + " " + interim).trim());
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
      setSpeaking(false);
      setBrowserPartial(pendingFinalRef.current);
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
  }, [socket.sendText, socket.sendSpeakingState, flushPending]);

  const toggleMic = useCallback(async () => {
    setMicError("");
    if (micOn) {
      stopMic();
      return;
    }
    const duplex = socket.serverSpeech?.mode === "duplex";
    if (socket.serverSpeech?.stt_available || duplex) {
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
    // Half-duplex (cascade mode only): echo cancellation does not cover the
    // page's own WebAudio playback, so an open mic transcribes the trainer's
    // voice and the app answers itself. Mute capture while trainer audio is
    // playing. In duplex mode the mic MUST stay open while the trainer talks
    // - overlap is the point - so PersonaPlex hears interruptions.
    if (socket.serverSpeech?.mode !== "duplex") {
      micRef.current?.setPaused(socket.speaking);
    }
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
  }, [socket.speaking, socket.serverSpeech]);

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
        <ReflectionCard sessionId={id} />
        <button className="primary" onClick={() => navigate("/")}>New session</button>
      </div>
    );
  }

  if (grounding !== "done") {
    return (
      <div className="page session">
        {grounding === "active" && <GroundingOverlay onDone={() => setGrounding("done")} />}
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
              voice: {socket.serverSpeech.mode === "duplex"
                ? "personaplex (full duplex)"
                : socket.serverSpeech.tts_engine ?? "browser"}
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
          {pressureLevel !== "off" && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={ambienceOn}
                onChange={(e) => setAmbienceOn(e.target.checked)}
              />
              Ambience
            </label>
          )}
          <button className="danger" onClick={socket.endSession} disabled={socket.ended}>
            End session
          </button>
        </div>
      </header>

      <div className="session-body">
        <div className="conversation" ref={logRef}>
          {socket.messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.role === "event" && (
                <span className="event-label">
                  {m.kind === "heckle" ? "Audience" : "Distraction"}
                  {m.interrupt ? " · interrupting" : ""}
                </span>
              )}
              {m.role === "assistant" ? <Markdown text={m.text} /> : m.text}
            </div>
          ))}
          {socket.partial && <div className="bubble user partial">{socket.partial}</div>}
          {browserPartial && <div className="bubble user partial">{browserPartial}</div>}
        </div>

        <aside className="side-panel">
          <TrainerAvatar getLevel={socket.getAudioLevel} speaking={socket.speaking} />
          {pressureLevel !== "off" && <CrowdStrip event={socket.pressureEvent} />}
          <CameraPanel onFrame={socket.sendFrame} rolling={socket.rolling} tip={socket.coachTip} />
          {socket.keyPoints.length > 0 && (
            <ul className="keypoint-list" aria-label="Key points">
              {socket.keyPoints.map((p) => (
                <li key={p.text} className={p.covered ? "covered" : ""}>
                  <span className="keypoint-mark">{p.covered ? "✓" : "○"}</span>
                  {p.text}
                </li>
              ))}
            </ul>
          )}
          <div className="mic-controls">
            <button className={micOn ? "danger" : "primary"} onClick={toggleMic} disabled={socket.ended}>
              {micOn ? "Mute microphone" : "Enable microphone"}
            </button>
            {socket.serverSpeech?.mode === "duplex" && !micOn && (
              <p className="hint">
                Full-duplex session: enable the microphone and just talk —
                you can interrupt the trainer any time. Headphones recommended.
              </p>
            )}
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
