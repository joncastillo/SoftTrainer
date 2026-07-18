# SoftTrainer

A soft skills practice app. Tell it what you want to rehearse, for example
"Help me practise a C++ interview" or "Practise negotiating a raise", and it
runs a live, time bounded roleplay session with voice, camera based behavior
feedback and a written assessment at the end.

## Features

- Free form scenarios: interviews, negotiations, difficult conversations,
  pitches, anything you can describe.
- Bidirectional voice: streaming speech to text with Kyutai
  (kyutai/stt-1b-en_fr) and natural text to speech with Kokoro 82M,
  spoken sentence by sentence while the reply is still being generated.
  Kyutai TTS is the second choice engine, and the browser speech APIs
  are the final fallback when neither is installed.
- Camera behavior assessment with MediaPipe: eye contact, gaze, blink rate,
  head stability, smile, and a rolling confidence score.
- Live behavior coaching: short, actionable on screen tips appear during the
  session (look at the camera more, keep your head steadier, relax your
  expression, center yourself in frame), plus the occasional bit of praise.
  Rule based and fully local, with cooldowns so it nudges rather than nags.
- Sessions are bounded like real meetings. The trainer wraps up naturally
  when time runs low and closes when it runs out.
- Final report: overall score, per dimension scores, strengths, concrete
  improvements, notable quotes, and presence metrics from the camera.
- Optional live subtitles for everything the trainer says.
- Everything persists to disk under `data/`: transcripts, behavior metrics,
  reports, uploaded documents, provider config and downloaded models.
- Self hosted models by default: the app downloads and runs Hugging Face
  models itself through transformers, no external inference server needed.
  OpenAI compatible endpoints (OpenAI, vLLM, LM Studio, llama.cpp server),
  Anthropic and Ollama remain available as optional providers in Settings.
- Document uploads (resume, job description, notes) with RAG: files are
  chunked, embedded and retrieved so the trainer references real details.
- Coding problems render as formatted markdown with syntax highlighted
  code blocks on screen, while the voice only speaks the prose.
- Model manager dialog: curated recommendations, a hub scan that rates
  each model's suitability (instruct tuned, size, gating, weight format),
  downloads with progress, and load/unload/delete controls. Loading a
  model automatically makes it the active provider.

## Layout

    backend/    FastAPI app: sessions, speech, vision, RAG, providers, hub
    frontend/   React + Vite app
    data/       created at runtime, all conversations and results live here

## Running

Backend (Python 3.10+):

    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt          # core, includes self hosted inference
    pip install -r requirements-full.txt     # optional: Kyutai speech, camera analysis
    python run.py

Frontend:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. For a production style setup, `npm run build`
and the backend will serve `frontend/dist` itself.

The backend starts on port 8000 and automatically moves to the next
free port (8001, 8002, ...) when it is taken. The frontend finds the
backend on its own by probing ports 8000 to 8019, so no configuration
is needed either way.

## Configuration

- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are picked up automatically by
  the default provider entries. Keys can also be entered in Settings and
  are stored in `data/config/providers.json`.
- `SOFTTRAINER_DATA` overrides the data directory location.
- The self hosted provider is active by default: open the model manager
  (Settings, or "Manage models" on the start page), download a
  recommended model and load it. Ollama and cloud providers can be
  activated in Settings instead.
- The active self hosted model is reloaded automatically when the backend
  starts, so a session works immediately after a restart. (The loaded model
  cache lives in memory, so without this the first session after a restart
  would have no replies until you reloaded the model by hand.)

## Optional dependencies

The app runs with the core requirements alone and degrades gracefully:

| Capability | Needs | Fallback |
| --- | --- | --- |
| Natural TTS (preferred) | kokoro, soundfile | Kyutai TTS, then browser speechSynthesis |
| Streaming STT | moshi | Browser SpeechRecognition |
| Camera analysis | mediapipe, opencv | Presence section omitted from reports |
| Dense embeddings | sentence-transformers | Hashed bag of words embeddings |

Self hosted inference (torch plus transformers) is part of the core
requirements since it is the default provider.

`GET /api/health` reports which capabilities are active on your install,
including which TTS engine is in use and why. The live session header
also shows the active voice ("voice: kokoro" means natural TTS is on,
"voice: browser" means the fallback voice is speaking).

## Windows notes

- Use Python 3.10 to 3.12. mediapipe and kokoro do not always ship
  wheels for the newest Python on Windows.
- **mediapipe is pinned to 0.10.14.** Later builds (0.10.35 and up) ship
  only the Tasks API and drop the legacy `solutions.face_mesh` used for
  camera analysis, which surfaces as "module mediapipe has no attribute
  solutions". If you upgrade it, camera feedback stops working.
- **No C/C++ compiler needed.** The Kyutai/moshi speech models and Kokoro
  call `torch.compile` at inference. On a machine without MSVC (`cl.exe`)
  that would raise "Compiler: cl is not found" and kill speech to text, so
  the backend forces eager execution (`TORCHDYNAMO_DISABLE`, set in
  `backend/app/config.py`). Speech runs a little slower but needs no
  compiler. Install Visual Studio Build Tools only if you want compiled
  kernels.
- Give the models room: the speech and self hosted LLM weights are several
  GB. A nearly full disk fails model downloads and caches in confusing ways.
- Kokoro needs no system espeak install, its phonemizer bundles one.
  After `pip install -r requirements-full.txt`, restart the backend and
  check `/api/health`: `speech.tts_engine` should say `kokoro`. If the
  voice still sounds robotic, the header badge will say `voice: browser`
  and the health endpoint explains what is missing.
- Without the server speech models, microphone input uses the browser
  recognizer, which works in Chrome and Edge and needs an internet
  connection. Firefox has no browser recognizer, type replies instead.
