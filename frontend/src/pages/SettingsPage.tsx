// Provider configuration and the local Hugging Face model manager.

import { useEffect, useState } from "react";
import { api } from "../api";
import { ModelManagerDialog } from "../components/ModelManagerDialog";
import type { ProviderConfig } from "../types";

const EMPTY: ProviderConfig = {
  id: "",
  kind: "openai-compatible",
  label: "",
  base_url: "",
  model: "",
  api_key: "",
  api_key_env: "",
  active: false,
};

export function SettingsPage() {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [editing, setEditing] = useState<ProviderConfig | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const [modelsOpen, setModelsOpen] = useState(false);

  const refresh = () => api.listProviders().then(setProviders);
  useEffect(() => {
    void refresh();
  }, []);

  const save = async () => {
    if (!editing || !editing.id || !editing.label) return;
    await api.saveProvider(editing);
    setEditing(null);
    void refresh();
  };

  const test = async (id: string) => {
    setTestResult((r) => ({ ...r, [id]: "testing..." }));
    try {
      const res = await api.testProvider(id);
      setTestResult((r) => ({ ...r, [id]: `ok: "${res.reply}"` }));
    } catch (e: any) {
      setTestResult((r) => ({ ...r, [id]: e.message }));
    }
  };

  return (
    <div className="page settings">
      <h1>Settings</h1>

      <section>
        <h2>LLM providers</h2>
        <table className="providers-table">
          <thead>
            <tr>
              <th>Provider</th><th>Type</th><th>Model</th><th>Active</th><th></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td>{p.kind}</td>
                <td>{p.model || "-"}</td>
                <td>
                  <input
                    type="radio"
                    name="active"
                    checked={p.active}
                    onChange={() => api.activateProvider(p.id).then(refresh)}
                  />
                </td>
                <td className="row-actions">
                  <button className="link" onClick={() => setEditing({ ...EMPTY, ...p })}>edit</button>
                  <button className="link" onClick={() => test(p.id)}>test</button>
                  <button
                    className="link danger"
                    onClick={() => api.deleteProvider(p.id).then(refresh)}
                  >
                    delete
                  </button>
                  {testResult[p.id] && <span className="hint"> {testResult[p.id]}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={() => setEditing({ ...EMPTY })}>Add provider</button>

        {editing && (
          <div className="editor">
            <label>Id<input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></label>
            <label>Label<input value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} /></label>
            <label>
              Type
              <select
                value={editing.kind}
                onChange={(e) => setEditing({ ...editing, kind: e.target.value as ProviderConfig["kind"] })}
              >
                <option value="openai-compatible">OpenAI compatible</option>
                <option value="anthropic">Anthropic</option>
                <option value="ollama">Ollama</option>
                <option value="local-hf">Local Hugging Face</option>
              </select>
            </label>
            <label>Base URL<input value={editing.base_url ?? ""} onChange={(e) => setEditing({ ...editing, base_url: e.target.value })} /></label>
            <label>Model<input value={editing.model} onChange={(e) => setEditing({ ...editing, model: e.target.value })} /></label>
            <label>API key<input type="password" value={editing.api_key ?? ""} onChange={(e) => setEditing({ ...editing, api_key: e.target.value })} /></label>
            <label>API key env var<input value={editing.api_key_env ?? ""} onChange={(e) => setEditing({ ...editing, api_key_env: e.target.value })} /></label>
            <div className="editor-actions">
              <button className="primary" onClick={save}>Save</button>
              <button onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Self hosted models</h2>
        <p className="hint">
          Models downloaded from Hugging Face run inside the app, no external
          server needed. Loading one makes it the active provider.
        </p>
        <button className="primary" onClick={() => setModelsOpen(true)}>
          Open model manager
        </button>
      </section>

      <ModelManagerDialog
        open={modelsOpen}
        onClose={() => setModelsOpen(false)}
        onChanged={() => void refresh()}
      />
    </div>
  );
}
