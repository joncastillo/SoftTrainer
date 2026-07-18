// Post-session reflection: three short CBT-style prompts saved with the session.

import { useState } from "react";
import { api } from "../api";

export const REFLECTION_QUESTIONS = [
  "What felt hardest in that session?",
  "What actually went better than it felt in the moment?",
  "What is one small thing you'll try next time?",
];

export function ReflectionCard({ sessionId }: { sessionId: string }) {
  const [answers, setAnswers] = useState<string[]>(REFLECTION_QUESTIONS.map(() => ""));
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setError("");
    try {
      await api.saveReflection(
        sessionId,
        REFLECTION_QUESTIONS.map((question, i) => ({
          question,
          answer: answers[i].trim(),
        })).filter((a) => a.answer),
      );
      setSaved(true);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (saved) {
    return <p className="hint reflection-saved">Reflection saved with this session. Nice work showing up.</p>;
  }

  return (
    <section className="reflection-card">
      <h3>A minute of reflection (optional)</h3>
      <p className="hint">
        Feelings in the moment are usually harsher than the facts. Writing two lines
        now makes the next session easier.
      </p>
      {REFLECTION_QUESTIONS.map((q, i) => (
        <label key={q}>
          {q}
          <textarea
            rows={2}
            value={answers[i]}
            onChange={(e) =>
              setAnswers((a) => a.map((v, j) => (j === i ? e.target.value : v)))
            }
          />
        </label>
      ))}
      {error && <p className="error">{error}</p>}
      <button onClick={save} disabled={answers.every((a) => !a.trim())}>
        Save reflection
      </button>
    </section>
  );
}
