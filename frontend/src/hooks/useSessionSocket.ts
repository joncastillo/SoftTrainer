// WebSocket state machine for one live training session.

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioQueue } from "../audio/player";
import type { BehaviorSummary, ChatMessage, Report } from "../types";

export interface ServerSpeech {
  stt_available: boolean;
  tts_available: boolean;
  tts_engine?: string | null;
  tts_detail?: string;
}

export interface SessionSocketState {
  connected: boolean;
  messages: ChatMessage[];
  partial: string;
  subtitle: string;
  secondsLeft: number | null;
  speaking: boolean;
  serverSpeech: ServerSpeech | null;
  rolling: BehaviorSummary | null;
  report: Report | null;
  generatingReport: boolean;
  ended: boolean;
  error: string | null;
}

export interface SessionSocketApi extends SessionSocketState {
  sendText: (text: string) => void;
  sendAudio: (pcm16b64: string) => void;
  endUtterance: () => void;
  sendFrame: (jpegB64: string) => void;
  endSession: () => void;
}

export function useSessionSocket(sessionId: string): SessionSocketApi {
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<AudioQueue | null>(null);
  const speechRef = useRef<ServerSpeech | null>(null);
  const [state, setState] = useState<SessionSocketState>({
    connected: false,
    messages: [],
    partial: "",
    subtitle: "",
    secondsLeft: null,
    speaking: false,
    serverSpeech: null,
    rolling: null,
    report: null,
    generatingReport: false,
    ended: false,
    error: null,
  });

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/session/${sessionId}`);
    wsRef.current = ws;
    const audio = new AudioQueue();
    audioRef.current = audio;
    audio.onStateChange = (speaking) => setState((s) => ({ ...s, speaking }));

    let disposed = false;
    ws.onopen = () => !disposed && setState((s) => ({ ...s, connected: true, error: null }));
    ws.onclose = () => !disposed && setState((s) => ({ ...s, connected: false }));
    ws.onerror = () => !disposed && setState((s) => ({ ...s, error: "Connection error" }));

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      // Side effects stay out of the state updater. StrictMode invokes
      // updaters twice in dev, which made TTS speak every reply twice.
      if (msg.type === "tts_audio") {
        audio.enqueueWavBase64(msg.wav_b64);
        return;
      }
      if (msg.type === "session_started") {
        speechRef.current = msg.speech;
      }
      if (msg.type === "assistant_message" && speechRef.current && !speechRef.current.tts_available) {
        audio.speakFallback(msg.spoken ?? msg.text);
      }

      setState((s) => {
        switch (msg.type) {
          case "session_started":
            return { ...s, secondsLeft: msg.seconds_left, serverSpeech: msg.speech };
          case "assistant_delta": {
            const messages = [...s.messages];
            const last = messages[messages.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              messages[messages.length - 1] = { ...last, text: last.text + msg.text };
            } else {
              messages.push({ role: "assistant", text: msg.text, streaming: true });
            }
            return { ...s, messages };
          }
          case "assistant_message": {
            const messages = s.messages.filter((m) => !m.streaming);
            messages.push({ role: "assistant", text: msg.text });
            return {
              ...s,
              messages,
              subtitle: msg.spoken ?? msg.text,
              secondsLeft: msg.seconds_left ?? s.secondsLeft,
            };
          }
          case "user_message":
            return { ...s, messages: [...s.messages, { role: "user", text: msg.text }], partial: "" };
          case "partial_transcript":
            return { ...s, partial: msg.text };
          case "metrics":
            return { ...s, rolling: msg.rolling };
          case "generating_report":
            return { ...s, generatingReport: true };
          case "session_ended":
            return { ...s, ended: true, generatingReport: false, report: msg.report };
          case "error":
            return { ...s, error: msg.message };
          default:
            return s;
        }
      });
    };

    return () => {
      disposed = true;
      ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
      ws.close();
      audio.stop();
    };
  }, [sessionId]);

  const send = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  return {
    ...state,
    sendText: useCallback((text: string) => send({ type: "user_text", text }), [send]),
    sendAudio: useCallback((pcm16_b64: string) => send({ type: "audio_chunk", pcm16_b64 }), [send]),
    endUtterance: useCallback(() => send({ type: "utterance_end" }), [send]),
    sendFrame: useCallback((jpeg_b64: string) => send({ type: "frame", jpeg_b64 }), [send]),
    endSession: useCallback(() => send({ type: "end" }), [send]),
  };
}
