# SoftTrainer

A soft skills practice app. Tell it what you want to rehearse, for example
"Help me practise a C++ interview" or "Practise negotiating a raise", and it
runs a live, time bounded roleplay session with voice, camera based behavior
feedback and a written assessment at the end.

## Features

- Free form scenarios: interviews, negotiations, difficult conversations,
  pitches, anything you can describe.
- Bidirectional voice with Kyutai models: streaming speech to text
  (kyutai/stt-1b-en_fr) and text to speech through the moshi package.
  Falls back to browser speech APIs when they are not installed.
- Camera behavior assessment with MediaPipe: eye contact, gaze, blink rate,
  head stability, smile, and a rolling confidence score.
- Sessions are bounded like real meetings. The trainer wraps up naturally
  when time runs low and closes when it runs out.
- Final report: overall score, per dimension scores, strengths, concrete
  improvements, notable quotes, and presence metrics from the camera.
- Optional live subtitles for everything the trainer says.
- Everything persists to disk under `data/`: transcripts, behavior metrics,
  reports, uploaded documents, provider config and downloaded models.
- Multiple LLM providers: OpenAI compatible endpoints (OpenAI, vLLM,
  LM Studio, llama.cpp server), Anthropic, Ollama, and fully local
  Hugging Face models. Add, test and switch providers in Settings.
- Document uploads (resume, job description, notes) with RAG: files are
  chunked, embedded and retrieved so the trainer references real details.
- Coding problems render as formatted markdown with syntax highlighted
  code blocks on screen, while the voice only speaks the prose.
- Built in Hugging Face model manager: search the hub, download models,
  load and unload them for local inference.

## Layout

    backend/    FastAPI app: sessions, speech, vision, RAG, providers, hub
    frontend/   React + Vite app
    data/       created at runtime, all conversations and results live here

## Running

Backend (Python 3.10+):

    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt          # core
    pip install -r requirements-full.txt     # optional: speech, vision, local LLMs
    python run.py

Frontend:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. For a production style setup, `npm run build`
and the backend will serve `frontend/dist` at http://localhost:8000.

## Configuration

- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are picked up automatically by
  the default provider entries. Keys can also be entered in Settings and
  are stored in `data/config/providers.json`.
- `SOFTTRAINER_DATA` overrides the data directory location.
- Ollama is the default active provider and expects a server on
  localhost:11434. Switch providers in Settings.

## Optional dependencies

The app runs with the core requirements alone and degrades gracefully:

| Capability | Needs | Fallback |
| --- | --- | --- |
| Kyutai STT/TTS | torch, moshi | Browser SpeechRecognition and speechSynthesis |
| Camera analysis | mediapipe, opencv | Presence section omitted from reports |
| Local HF inference | transformers, accelerate | Cloud or Ollama providers |
| Dense embeddings | sentence-transformers | Hashed bag of words embeddings |

`GET /api/health` reports which capabilities are active on your install.
