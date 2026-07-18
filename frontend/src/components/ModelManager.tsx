// Search the Hugging Face hub, download models, load them for inference.

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { HubModel, LocalModel } from "../types";

function formatSize(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

export function ModelManager() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HubModel[]>([]);
  const [local, setLocal] = useState<LocalModel[]>([]);
  const [busy, setBusy] = useState<Record<string, string>>({});
  const pollers = useRef<Record<string, number>>({});

  const refreshLocal = () => api.localModels().then(setLocal);
  useEffect(() => {
    void refreshLocal();
    const timers = pollers.current;
    return () => Object.values(timers).forEach(clearInterval);
  }, []);

  const search = async () => {
    if (!query.trim()) return;
    setBusy((b) => ({ ...b, search: "searching..." }));
    try {
      setResults(await api.searchModels(query.trim()));
      setBusy(({ search: _drop, ...rest }) => rest);
    } catch (e: any) {
      setBusy((b) => ({ ...b, search: e.message }));
    }
  };

  const download = async (repoId: string) => {
    await api.downloadModel(repoId);
    setBusy((b) => ({ ...b, [repoId]: "downloading..." }));
    pollers.current[repoId] = window.setInterval(async () => {
      const status = await api.downloadStatus(repoId);
      if (status.status === "done" || status.status === "error") {
        clearInterval(pollers.current[repoId]);
        delete pollers.current[repoId];
        setBusy((b) => ({
          ...b,
          [repoId]: status.status === "done" ? "downloaded" : `error: ${status.message}`,
        }));
        void refreshLocal();
        setResults((rs) => rs.map((r) =>
          r.repo_id === repoId ? { ...r, downloaded: status.status === "done" } : r));
      }
    }, 3000);
  };

  const act = async (repoId: string, fn: () => Promise<unknown>, label: string) => {
    setBusy((b) => ({ ...b, [repoId]: label }));
    try {
      await fn();
      setBusy(({ [repoId]: _drop, ...rest }) => rest);
    } catch (e: any) {
      setBusy((b) => ({ ...b, [repoId]: e.message }));
    }
    void refreshLocal();
  };

  return (
    <div className="model-manager">
      <div className="search-row">
        <input
          value={query}
          placeholder="Search text generation models, e.g. qwen 3b instruct"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button onClick={search}>Search hub</button>
        {busy.search && <span className="hint">{busy.search}</span>}
      </div>

      {results.length > 0 && (
        <table className="models-table">
          <thead>
            <tr><th>Model</th><th>Downloads</th><th>Likes</th><th></th></tr>
          </thead>
          <tbody>
            {results.map((m) => (
              <tr key={m.repo_id}>
                <td>{m.repo_id}</td>
                <td>{m.downloads.toLocaleString()}</td>
                <td>{m.likes}</td>
                <td>
                  {m.downloaded ? (
                    <span className="hint">on disk</span>
                  ) : (
                    <button className="link" onClick={() => download(m.repo_id)}>download</button>
                  )}
                  {busy[m.repo_id] && <span className="hint"> {busy[m.repo_id]}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>On disk</h3>
      <table className="models-table">
        <thead>
          <tr><th>Model</th><th>Size</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {local.map((m) => (
            <tr key={m.repo_id}>
              <td>{m.repo_id}</td>
              <td>{formatSize(m.size_bytes)}</td>
              <td>{m.loaded ? "loaded" : "not loaded"}</td>
              <td className="row-actions">
                {m.loaded ? (
                  <button className="link" onClick={() => act(m.repo_id, () => api.unloadModel(m.repo_id), "unloading...")}>
                    unload
                  </button>
                ) : (
                  <button className="link" onClick={() => act(m.repo_id, () => api.loadModel(m.repo_id), "loading...")}>
                    load
                  </button>
                )}
                <button className="link danger" onClick={() => act(m.repo_id, () => api.deleteModel(m.repo_id), "deleting...")}>
                  delete
                </button>
                {busy[m.repo_id] && <span className="hint"> {busy[m.repo_id]}</span>}
              </td>
            </tr>
          ))}
          {local.length === 0 && (
            <tr><td colSpan={4} className="hint">No models downloaded yet.</td></tr>
          )}
        </tbody>
      </table>
      <p className="hint">
        To chat with a loaded model, set the "Local Hugging Face model" provider's
        model field to its repo id and activate it.
      </p>
    </div>
  );
}
