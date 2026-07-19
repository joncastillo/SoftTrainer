// Plays wav blobs from the server in order. Falls back to the browser
// speech synthesis voice when the server has no TTS model installed.

export class AudioQueue {
  private ctx = new AudioContext();
  private queue: ArrayBuffer[] = [];
  private playing = false;
  private analyser: AnalyserNode;
  private levelBuf: Uint8Array<ArrayBuffer>;
  onStateChange?: (speaking: boolean) => void;

  constructor() {
    // All playback routes through an analyser so the trainer avatar can
    // lip-sync to whatever is actually coming out of the speakers.
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.ctx.destination);
    this.levelBuf = new Uint8Array(this.analyser.frequencyBinCount);
  }

  /** Current playback loudness, 0..1, for driving the avatar mouth. */
  getLevel(): number {
    if (!this.playing || this.ctx.state !== "running") return 0;
    this.analyser.getByteTimeDomainData(this.levelBuf);
    let sum = 0;
    for (const v of this.levelBuf) {
      const c = (v - 128) / 128;
      sum += c * c;
    }
    return Math.min(1, Math.sqrt(sum / this.levelBuf.length) * 4);
  }

  enqueueWavBase64(b64: string) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    this.queue.push(bytes.buffer);
    void this.drain();
  }

  // --- Full-duplex streaming channel -----------------------------------
  // PersonaPlex sends a continuous stream of small PCM chunks (including
  // silence). Chunks are scheduled back to back on the context clock with
  // a small jitter buffer; the analyser still drives the avatar mouth.
  private streamAt = 0;
  private streamEndTimer: number | undefined;
  private pendingSources: AudioBufferSourceNode[] = [];
  // Max seconds of audio scheduled ahead of the clock. Without a cap,
  // every burst or hiccup grows the gap between the model speaking and
  // the user hearing it, and the lag compounds for the whole session.
  private static MAX_AHEAD = 0.35;

  enqueuePcm16Base64(b64: string, sampleRate: number) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const i16 = new Int16Array(bytes.buffer, 0, bytes.byteLength >> 1);
    if (i16.length === 0) return;
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const buf = this.ctx.createBuffer(1, f32.length, sampleRate);
    buf.getChannelData(0).set(f32);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.analyser);
    const now = this.ctx.currentTime;
    // Re-arm the jitter buffer after an underrun or on the first chunk.
    if (this.streamAt < now + 0.02) this.streamAt = now + 0.1;
    // Latency cap: if playback has drifted too far behind, drop what is
    // queued and resync close to the clock. Losing a syllable beats a
    // conversation that runs seconds behind.
    if (this.streamAt - now > AudioQueue.MAX_AHEAD) {
      for (const s of this.pendingSources) {
        try { s.stop(); } catch { /* already done */ }
      }
      this.pendingSources = [];
      this.streamAt = now + 0.1;
    }
    src.onended = () => {
      const i = this.pendingSources.indexOf(src);
      if (i >= 0) this.pendingSources.splice(i, 1);
    };
    this.pendingSources.push(src);
    src.start(this.streamAt);
    this.streamAt += buf.duration;
    if (!this.playing) {
      this.playing = true;
      this.onStateChange?.(true);
    }
    if (this.streamEndTimer !== undefined) clearTimeout(this.streamEndTimer);
    this.streamEndTimer = window.setTimeout(() => {
      this.playing = false;
      this.onStateChange?.(false);
    }, (this.streamAt - now) * 1000 + 300);
  }

  /** Heckler channel: plays immediately, over anything else — including the
   *  user speaking. It bypasses the trainer queue, the speaking state and
   *  the avatar analyser, because the interruption is the point. */
  playInterruptWavBase64(b64: string) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    void this.ctx.decodeAudioData(bytes.buffer).then((audio) => {
      const src = this.ctx.createBufferSource();
      src.buffer = audio;
      src.connect(this.ctx.destination);
      src.start();
    }).catch(() => {
      /* skip undecodable chunk */
    });
  }

  private async drain() {
    if (this.playing) return;
    this.playing = true;
    this.onStateChange?.(true);
    while (this.queue.length > 0) {
      const buf = this.queue.shift()!;
      try {
        const audio = await this.ctx.decodeAudioData(buf.slice(0));
        await new Promise<void>((resolve) => {
          const src = this.ctx.createBufferSource();
          src.buffer = audio;
          src.connect(this.analyser);
          src.onended = () => resolve();
          src.start();
        });
      } catch {
        /* skip undecodable chunk */
      }
    }
    this.playing = false;
    this.onStateChange?.(false);
  }

  /** Browser-voice heckle: speaks without touching the speaking state so
   *  recognition keeps listening while the user is being talked over. */
  speakInterruptFallback(text: string) {
    if (!("speechSynthesis" in window) || !text.trim()) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 0.8;
    window.speechSynthesis.speak(utterance);
  }

  speakFallback(text: string) {
    if (!("speechSynthesis" in window) || !text.trim()) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    this.onStateChange?.(true);
    utterance.onend = () => this.onStateChange?.(false);
    window.speechSynthesis.speak(utterance);
  }

  stop() {
    this.queue = [];
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    void this.ctx.close();
  }
}
