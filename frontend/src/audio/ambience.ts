// Procedural room ambience for pressure sessions: a low noise bed plus a
// band-passed murmur that swells and fades like a restless audience. All
// generated locally with WebAudio, no assets.

const LEVEL_GAIN: Record<string, number> = { low: 0.025, medium: 0.045, high: 0.07 };

function noiseBuffer(ctx: AudioContext, seconds: number): AudioBuffer {
  const buf = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
  const data = buf.getChannelData(0);
  let last = 0;
  for (let i = 0; i < data.length; i++) {
    // Brown-ish noise: integrate white noise, keep it bounded.
    const white = Math.random() * 2 - 1;
    last = (last + 0.02 * white) / 1.02;
    data[i] = last * 3.5;
  }
  return buf;
}

export class Ambience {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private murmur: GainNode | null = null;
  private lfoTimer: number | null = null;
  private resumeHook: (() => void) | null = null;
  private levelGain = 0;

  start(level: string) {
    const gain = LEVEL_GAIN[level];
    if (!gain || this.ctx) return;
    this.levelGain = gain;
    const ctx = new AudioContext();
    this.ctx = ctx;

    this.master = ctx.createGain();
    this.master.gain.value = gain;
    this.master.connect(ctx.destination);

    const noise = noiseBuffer(ctx, 4);

    // Low room-tone bed.
    const bed = ctx.createBufferSource();
    bed.buffer = noise;
    bed.loop = true;
    const bedFilter = ctx.createBiquadFilter();
    bedFilter.type = "lowpass";
    bedFilter.frequency.value = 220;
    bed.connect(bedFilter).connect(this.master);
    bed.start();

    // Voice-band murmur with a slow random swell.
    const talk = ctx.createBufferSource();
    talk.buffer = noise;
    talk.loop = true;
    // A slight detune keeps the two loops from phasing in sync.
    talk.playbackRate.value = 1.31;
    const talkFilter = ctx.createBiquadFilter();
    talkFilter.type = "bandpass";
    talkFilter.frequency.value = 500;
    talkFilter.Q.value = 0.8;
    this.murmur = ctx.createGain();
    this.murmur.gain.value = 0.4;
    talk.connect(talkFilter).connect(this.murmur).connect(this.master);
    talk.start();

    const swell = () => {
      if (!this.ctx || !this.murmur) return;
      const target = 0.15 + Math.random() * 0.85;
      this.murmur.gain.linearRampToValueAtTime(
        target, this.ctx.currentTime + 1.5 + Math.random() * 2);
      this.lfoTimer = window.setTimeout(swell, 2000 + Math.random() * 3000);
    };
    swell();

    // Autoplay policies may hold the context until a user gesture.
    if (ctx.state !== "running") {
      this.resumeHook = () => void ctx.resume();
      window.addEventListener("pointerdown", this.resumeHook, { once: true });
      window.addEventListener("keydown", this.resumeHook, { once: true });
    }
  }

  setMuted(muted: boolean) {
    if (this.master && this.ctx) {
      this.master.gain.setTargetAtTime(
        muted ? 0 : this.levelGain, this.ctx.currentTime, 0.2);
    }
  }

  stop() {
    if (this.lfoTimer) clearTimeout(this.lfoTimer);
    if (this.resumeHook) {
      window.removeEventListener("pointerdown", this.resumeHook);
      window.removeEventListener("keydown", this.resumeHook);
    }
    void this.ctx?.close();
    this.ctx = null;
    this.master = null;
    this.murmur = null;
  }
}
