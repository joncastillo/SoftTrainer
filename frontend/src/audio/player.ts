// Plays wav blobs from the server in order. Falls back to the browser
// speech synthesis voice when the server has no TTS model installed.

export class AudioQueue {
  private ctx = new AudioContext();
  private queue: ArrayBuffer[] = [];
  private playing = false;
  onStateChange?: (speaking: boolean) => void;

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
          src.connect(this.ctx.destination);
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
