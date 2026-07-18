# SoftTrainer roadmap

## Vision

Grow SoftTrainer from a spoken interview roleplay into a **communication and
composure gym**: a rehearsal environment under controllable pressure where
someone practises a hard social situation, gets objective feedback on how they
came across, and progressively hardens against anxiety, distraction, and losing
their train of thought.

Target problems:

- Poor communication skills
- Social anxiety
- Losing your train of thought mid-way
- Being easily distracted / staying focused
- Handling hecklers and hostile audiences under pressure

Principles: **local-first** (face, voice and anxiety data is sensitive),
**supportive not judgemental** (anxious users are vulnerable; this is not a
medical device), and **grounded metrics** (avoid pseudoscience, let users
calibrate).

## Where we are today

- Free-form single-counterpart roleplay, time bounded, with a written report.
- Bidirectional voice: Kyutai STT, Kokoro TTS, browser fallbacks.
- Camera behavior sensing via MediaPipe (eye contact, head pose, expression,
  confidence) and a **live rule-based coaching layer** (`backend/app/vision/coach.py`)
  that surfaces on-screen tips during the session, including sustained
  gaze-off-screen ("you drifted") detection.
- Speech delivery analysis (`backend/app/sessions/delivery.py`): filler words
  and speaking pace, live tips plus a report section.
- Key points + lost-thread coaching (`backend/app/sessions/keypoints.py`):
  the user sets up to five points, a live checklist tracks lexical coverage,
  thread-loss moments get a recovery tip anchored to the next uncovered point.
- Longitudinal progress view: `/api/progress` + a Progress page with
  per-metric trend tiles and a session table.
- RAG document grounding; self-hosted or cloud LLM providers.

## Capability map

| Pillar | Have | Need |
| --- | --- | --- |
| Scenarios & programs | Single scenarios, difficulty flag | Scenario library; graded exposure ladders; multi-session curricula |
| Interlocutors | 1 LLM counterpart | Multi-agent: counterpart + heckler/distraction director + audience |
| Embodiment | Webcam self-view | Talking-head avatar (lip-sync to TTS); scripted crowd; ambient audio |
| Nonverbal sensing | Eye contact / head pose / smile + live coach | Posture, fidget, gaze-off-screen (distraction), optional rPPG arousal |
| Speech sensing | STT transcript | Word timings + prosody: fillers, pace (WPM), pauses, monotone, volume |
| Content sensing | End-of-session report | Key-point coverage; coherence; "lost your thread" detection |
| Coaching engine | Rule-based nonverbal tips | Speech tips, focus-recovery tips, freeze/forget recovery prompts |
| Anxiety layer | — | Exposure ladder, grounding, CBT reflection, streaks, disclaimers |
| Memory/recall | — | Structure drills, fading cue cards, key-point tracking |
| Progress | Per-session report | Longitudinal dashboards, goals, gamification |

## Phases

- **Phase 1 — deepen sensing & coaching (local, no new heavy tech).** Speech
  analytics (fillers, WPM, pauses); extend the live coach to speech + focus;
  "set your key points -> did you cover them / did you lose your thread";
  longitudinal progress view. *Done (pauses/prosody still open).*
- **Phase 2 — pressure & anxiety.** Heckler/distraction director +
  audience as audio + on-screen text; composure-under-pressure scoring;
  anxiety layer (grounding breath, exposure ladder, reflection). *First
  version done: scripted director (`backend/app/sessions/pressure.py`);
  an LLM-driven multi-agent director is the natural upgrade.*
- **Phase 3 — embodiment.** Talking-head lip-synced to Kokoro; scripted
  crowd; ambient soundscapes. *First version done, deliberately light:
  a stylized SVG head driven by a WebAudio analyser, a reactive crowd
  strip, and procedural room ambience. Photoreal/3D avatars
  (SadTalker/LivePortrait or engine-based) remain the upgrade path.*
- **Phase 4 — immersion.** Unity/WebXR (VR) audience for real presence;
  photoreal environments; advanced avatars. *Not started: needs a game
  engine project, 3D assets, and headset hardware for testing — out of
  reach of the local web stack by design.*

## Technology notes

- **Avatars, not Gaussian splatting (at first).** For a talking interviewer,
  use audio-driven talking-head models (SadTalker/Wav2Lip/LivePortrait, or a
  game-engine MetaHuman + Audio2Face) driven by the TTS audio. For an audience,
  use a game engine with instanced crowd characters playing scripted reactions
  (which also powers heckler/distraction training). 3D Gaussian splatting is for
  photoreal *environments* (novel-view rendering of a captured room/stage);
  reserve it, and animatable-Gaussian head avatars, for Phase 4. For anxiety
  specifically, VR presence (a headset) is the proven exposure modality.
- **Performance.** Avatar + STT + TTS + vision + LLM at once is GPU-heavy.
  Offload avatars to the client (WebGL), stream everything, keep cloud models
  as an option. Phase 1 deliberately needs none of this.
