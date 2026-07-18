// Microphone capture: resamples to 24 kHz PCM16 and reports voice
// activity so the app can detect the end of an utterance.

export interface MicHandle {
  stop: () => void;
}

const TARGET_RATE = 24000;

function downsample(input: Float32Array, fromRate: number): Float32Array {
  if (fromRate === TARGET_RATE) return input;
  const ratio = fromRate / TARGET_RATE;
  const length = Math.floor(input.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    out[i] = input[Math.floor(i * ratio)];
  }
  return out;
}

function toPcm16Base64(samples: Float32Array): string {
  const buf = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(buf.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export async function startMic(
  onChunk: (pcm16b64: string) => void,
  onSpeechEnd: () => void,
): Promise<MicHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);

  let silentMs = 0;
  let speaking = false;

  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    const rms = Math.sqrt(input.reduce((a, v) => a + v * v, 0) / input.length);
    const frameMs = (input.length / ctx.sampleRate) * 1000;

    if (rms > 0.015) {
      speaking = true;
      silentMs = 0;
    } else if (speaking) {
      silentMs += frameMs;
      if (silentMs > 900) {
        speaking = false;
        silentMs = 0;
        onSpeechEnd();
      }
    }
    onChunk(toPcm16Base64(downsample(new Float32Array(input), ctx.sampleRate)));
  };

  source.connect(processor);
  processor.connect(ctx.destination);

  return {
    stop: () => {
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
