// New session form: scenario, provider, bounds, subtitles, documents.

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ModelManagerDialog } from "../components/ModelManagerDialog";
import type { DocumentMeta, ProviderConfig } from "../types";

const EXAMPLES = [
  "Help me practise a C++ technical interview",
  "Practise negotiating a salary raise with my manager",
  "Rehearse delivering difficult feedback to a teammate",
  "Practise a startup pitch to a skeptical investor",
];

export function SetupPage() {
  const navigate = useNavigate();
  const [scenario, setScenario] = useState("");
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [providerId, setProviderId] = useState<string>("");
  const [minutes, setMinutes] = useState(15);
  const [difficulty, setDifficulty] = useState("medium");
  const [subtitles, setSubtitles] = useState(true);
  const [pressure, setPressure] = useState("off");
  const [grounding, setGrounding] = useState(false);
  const [keyPoints, setKeyPoints] = useState<string[]>(["", "", ""]);
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [modelsOpen, setModelsOpen] = useState(false);

  const refreshProviders = useCallback(() => {
    api.listProviders().then((ps) => {
      setProviders(ps);
      setProviderId((cur) => cur || ps.find((p) => p.active)?.id || "");
    });
  }, []);

  useEffect(() => {
    refreshProviders();
    api.listDocuments().then(setDocuments);
  }, [refreshProviders]);

  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
      const meta = await api.uploadDocument(file);
      setDocuments((d) => [...d, meta]);
      setSelectedDocs((s) => [...s, meta.id]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const start = async () => {
    setError("");
    try {
      const { id } = await api.createSession({
        scenario,
        provider_id: providerId || null,
        duration_minutes: minutes,
        subtitles,
        document_ids: selectedDocs,
        difficulty,
        key_points: keyPoints.map((p) => p.trim()).filter(Boolean),
        pressure,
        grounding,
      });
      navigate(`/session/${id}`);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="page setup">
      <h1>Start a practice session</h1>
      <p className="hint">
        Describe what you want to practise. The trainer roleplays the other side,
        keeps time like a real meeting, and gives you a full assessment at the end.
      </p>

      <textarea
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        placeholder='For example: "Help me practise a C++ interview"'
        rows={3}
      />
      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" onClick={() => setScenario(ex)}>
            {ex}
          </button>
        ))}
      </div>

      <div className="form-row">
        <label>
          Provider
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label} ({p.model || "no model"})
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => setModelsOpen(true)}>Manage models</button>
        <label>
          Length
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
            {[5, 10, 15, 20, 30, 45, 60].map((m) => (
              <option key={m} value={m}>{m} minutes</option>
            ))}
          </select>
        </label>
        <label>
          Difficulty
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>
        <label title="Occasional audience heckles and room distractions to practise composure">
          Pressure
          <select value={pressure} onChange={(e) => setPressure(e.target.value)}>
            <option value="off">Off</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />
          Subtitles
        </label>
        <label className="checkbox" title="A 30-second guided breath before the trainer starts">
          <input type="checkbox" checked={grounding} onChange={(e) => setGrounding(e.target.checked)} />
          Grounding breath
        </label>
      </div>

      <section>
        <h3>Key points (optional)</h3>
        <p className="hint">
          Up to five points you want to land. They show as a subtle checklist during
          the session, and the coach nudges you if one is still missing near the end.
        </p>
        {keyPoints.map((p, i) => (
          <input
            key={i}
            className="keypoint-input"
            value={p}
            placeholder={`Key point ${i + 1}`}
            maxLength={120}
            onChange={(e) =>
              setKeyPoints((ks) => ks.map((k, j) => (j === i ? e.target.value : k)))
            }
          />
        ))}
        {keyPoints.length < 5 && (
          <button className="link" onClick={() => setKeyPoints((ks) => [...ks, ""])}>
            + add another
          </button>
        )}
      </section>

      <section>
        <h3>Documents (resume, job description, notes)</h3>
        <input
          type="file"
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        />
        {uploading && <span className="hint">Uploading and indexing...</span>}
        <ul className="doc-list">
          {documents.map((d) => (
            <li key={d.id}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={selectedDocs.includes(d.id)}
                  onChange={(e) =>
                    setSelectedDocs((s) =>
                      e.target.checked ? [...s, d.id] : s.filter((x) => x !== d.id),
                    )
                  }
                />
                {d.filename} ({d.chunks} chunks)
              </label>
              <button
                className="link danger"
                onClick={() => {
                  void api.deleteDocument(d.id);
                  setDocuments((docs) => docs.filter((x) => x.id !== d.id));
                  setSelectedDocs((s) => s.filter((x) => x !== d.id));
                }}
              >
                delete
              </button>
            </li>
          ))}
        </ul>
      </section>

      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={scenario.trim().length < 3} onClick={start}>
        Start session
      </button>

      <ModelManagerDialog
        open={modelsOpen}
        onClose={() => setModelsOpen(false)}
        onChanged={refreshProviders}
      />
    </div>
  );
}
