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
