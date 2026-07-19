// WebSocket state machine for one live training session.

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioQueue } from "../audio/player";
import { backendWsBase } from "../backend";
import type { BehaviorSummary, ChatMessage, CoachTip, KeyPointState, Report } from "../types";

export interface ServerSpeech {
  stt_available: boolean;
  tts_available: boolean;
  tts_engine?: string | null;
  tts_detail?: string;
  /** "duplex" when PersonaPlex owns the conversation, else "cascade". */
  mode?: string;
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
  coachTip: CoachTip | null;
  keyPoints: KeyPointState[];
  pressureEvent: { id: number; kind: string } | null;
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
  getAudioLevel: () => number;
  sendSpeakingState: (active: boolean) => void;
}

export function useSessionSocket(sessionId: string, enabled: boolean = true): SessionSocketApi {
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
    coachTip: null,
    keyPoints: [],
    pressureEvent: null,
    report: null,
    generatingReport: false,
    ended: false,
    error: null,
  });

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let disposed = false;
    const audio = new AudioQueue();
    audioRef.current = audio;
    audio.onStateChange = (speaking) => setState((s) => ({ ...s, speaking }));

    const connect = (wsBase: string) => {
      if (disposed) return;
      ws = new WebSocket(`${wsBase}/ws/session/${sessionId}`);
      wsRef.current = ws;
      attach(ws);
    };
    backendWsBase()
      .then(connect)
      .catch((e: Error) => !disposed && setState((s) => ({ ...s, error: e.message })));

    const attach = (ws: WebSocket) => {
      ws.onopen = () => !disposed && setState((s) => ({ ...s, connected: true, error: null }));
      ws.onclose = () => !disposed && setState((s) => ({ ...s, connected: false }));
      ws.onerror = () => !disposed && setState((s) => ({ ...s, error: "Connection error" }));
      ws.onmessage = onMessage;
    };

    const onMessage = (event: MessageEvent) => {
      const msg = JSON.parse(event.data);

      // Side effects stay out of the state updater. StrictMode invokes
      // updaters twice in dev, which made TTS speak every reply twice.
      if (msg.type === "tts_audio") {
        if (msg.channel === "heckler") {
          audio.playInterruptWavBase64(msg.wav_b64);
        } else {
          audio.enqueueWavBase64(msg.wav_b64);
        }
        return;
      }
      if (msg.type === "duplex_audio") {
        audio.enqueuePcm16Base64(msg.pcm16_b64, msg.sample_rate ?? 24000);
        return;
      }
      if (msg.type === "session_started") {
        speechRef.current = msg.speech;
      }
      if (msg.type === "assistant_message" && speechRef.current && !speechRef.current.tts_available) {
        audio.speakFallback(msg.spoken ?? msg.text);
      }
      if (msg.type === "pressure_event" && msg.kind === "heckle" &&
          speechRef.current && !speechRef.current.tts_available) {
        audio.speakInterruptFallback(msg.text);
      }

      setState((s) => {
        switch (msg.type) {
          case "session_started":
            return {
              ...s,
              secondsLeft: msg.seconds_left,
              serverSpeech: msg.speech,
              keyPoints: msg.key_points ?? [],
            };
          case "key_points":
            return { ...s, keyPoints: msg.points ?? [] };
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
          case "pressure_event":
            return {
              ...s,
              messages: [...s.messages,
                { role: "event", text: msg.text, kind: msg.kind, interrupt: msg.interrupt }],
              pressureEvent: { id: (s.pressureEvent?.id ?? 0) + 1, kind: msg.kind },
            };
          case "partial_transcript":
            return { ...s, partial: msg.text };
          case "metrics":
            return { ...s, rolling: msg.rolling };
          case "coach_tip":
            return {
              ...s,
              coachTip: {
                id: (s.coachTip?.id ?? 0) + 1,
                text: msg.text,
                kind: msg.kind,
                tone: msg.tone,
              },
            };
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
      if (ws) {
        ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
        ws.close();
      }
      audio.stop();
    };
  }, [sessionId, enabled]);

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
    getAudioLevel: useCallback(() => audioRef.current?.getLevel() ?? 0, []),
    sendSpeakingState: useCallback(
      (active: boolean) => send({ type: "speaking_state", active }), [send]),
  };
}
