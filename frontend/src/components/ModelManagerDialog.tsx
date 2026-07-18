// Modal dialog for managing self hosted models: browse recommended
// picks, scan the hub, download with progress, load, unload, delete.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { HubModel, LocalModel, RecommendedModel } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  onChanged?: () => void;
}

type Tab = "recommended" | "search" | "disk";

function formatSize(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

export function ModelManagerDialog({ open, onClose, onChanged }: Props) {
  const [tab, setTab] = useState<Tab>("recommended");
  const [recommended, setRecommended] = useState<RecommendedModel[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HubModel[]>([]);
  const [local, setLocal] = useState<LocalModel[]>([]);
  const [status, setStatus] = useState<Record<string, string>>({});
  const [progress, setProgress] = useState<Record<string, number | null>>({});
  const timers = useRef<Record<string, number>>({});

  const refresh = useCallback(() => {
    void api.recommendedModels().then(setRecommended);
    void api.localModels().then(setLocal);
    onChanged?.();
  }, [onChanged]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  useEffect(() => {
    const t = timers.current;
    return () => Object.values(t).forEach(clearInterval);
  }, []);

  const clearTimer = (repoId: string) => {
    if (timers.current[repoId]) {
      clearInterval(timers.current[repoId]);
      delete timers.current[repoId];
    }
  };

  const download = async (repoId: string) => {
    setStatus((s) => ({ ...s, [repoId]: "downloading" }));
    setProgress((p) => ({ ...p, [repoId]: null }));
    await api.downloadModel(repoId);
    clearTimer(repoId);
    timers.current[repoId] = window.setInterval(async () => {
      const st = await api.downloadStatus(repoId);
      if (st.status === "downloading") {
        setProgress((p) => ({
          ...p,
          [repoId]: st.total_bytes ? (st.downloaded_bytes ?? 0) / st.total_bytes : null,
        }));
        return;
      }
      clearTimer(repoId);
      setProgress((p) => ({ ...p, [repoId]: undefined as any }));
      setStatus((s) => ({
        ...s,
        [repoId]: st.status === "done" ? "downloaded" : `error: ${st.message}`,
      }));
      refresh();
      setResults((rs) =>
        rs.map((r) => (r.repo_id === repoId ? { ...r, downloaded: st.status === "done" } : r)),
      );
    }, 2500);
  };

  const load = async (repoId: string) => {
    setStatus((s) => ({ ...s, [repoId]: "loading into memory" }));
    try {
      await api.loadModel(repoId);
    } catch (e: any) {
      setStatus((s) => ({ ...s, [repoId]: `error: ${e.message}` }));
      return;
    }
    clearTimer(repoId);
    timers.current[repoId] = window.setInterval(async () => {
      const st = await api.loadStatus(repoId);
      if (st.status === "loading") return;
      clearTimer(repoId);
      setStatus((s) => ({
        ...s,
        [repoId]: st.status === "done" ? "loaded, now the active provider" : `error: ${st.message}`,
      }));
      refresh();
    }, 2000);
  };

  const unload = async (repoId: string) => {
    await api.unloadModel(repoId);
    setStatus((s) => ({ ...s, [repoId]: "unloaded" }));
    refresh();
  };

  const remove = async (repoId: string) => {
    await api.deleteModel(repoId);
    setStatus((s) => ({ ...s, [repoId]: "deleted" }));
    refresh();
  };

  const search = async () => {
    if (!query.trim()) return;
    setStatus((s) => ({ ...s, _search: "scanning the hub..." }));
    try {
      setResults(await api.searchModels(query.trim()));
      setStatus(({ _search, ...rest }) => rest);
    } catch (e: any) {
      setStatus((s) => ({ ...s, _search: e.message }));
    }
  };

  const actions = (repoId: string, downloaded: boolean, loaded: boolean, gated?: boolean) => (
    <div className="model-actions">
      {!downloaded && (
        <button className="link" disabled={gated} onClick={() => download(repoId)}>
          download
        </button>
      )}
      {downloaded && !loaded && (
        <>
          <button className="link" onClick={() => load(repoId)}>load</button>
          <button className="link danger" onClick={() => remove(repoId)}>delete</button>
        </>
      )}
      {loaded && <button className="link" onClick={() => unload(repoId)}>unload</button>}
    </div>
  );

  const statusLine = (repoId: string) => (
    <>
      {status[repoId] && (
        <div className={`model-status ${status[repoId].startsWith("error") ? "error" : ""}`}>
          {status[repoId]}
          {progress[repoId] != null && ` ${Math.round((progress[repoId] as number) * 100)}%`}
        </div>
      )}
      {status[repoId] === "downloading" && (
        <div className="bar">
          <div
            className={`bar-fill ${progress[repoId] == null ? "indeterminate" : ""}`}
            style={{ width: `${Math.round(((progress[repoId] as number) ?? 0.15) * 100)}%` }}
          />
        </div>
      )}
    </>
  );

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Model manager</h2>
          <button className="link" onClick={onClose}>close</button>
        </header>
        <p className="hint">
          Models run inside the app itself. Loading a model makes it the active
          provider for new sessions.
        </p>

        <div className="tabs">
          <button className={tab === "recommended" ? "active" : ""} onClick={() => setTab("recommended")}>
            Recommended
          </button>
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>
            Scan hub
          </button>
          <button className={tab === "disk" ? "active" : ""} onClick={() => setTab("disk")}>
            On disk
          </button>
        </div>

        <div className="modal-body">
          {tab === "recommended" && (
            <ul className="model-list">
              {recommended.map((m) => (
                <li key={m.repo_id}>
                  <div className="model-info">
                    <div className="model-name">
                      {m.repo_id} <span className="tag">{m.params}</span>
                      {m.loaded && <span className="tag ok">loaded</span>}
                      {!m.loaded && m.downloaded && <span className="tag">on disk</span>}
                      {m.gated && <span className="tag warn">gated</span>}
                    </div>
                    <div className="hint">{m.note}</div>
                    {statusLine(m.repo_id)}
                  </div>
                  {actions(m.repo_id, m.downloaded, m.loaded, m.gated)}
                </li>
              ))}
            </ul>
          )}

          {tab === "search" && (
            <>
              <div className="search-row">
                <input
                  value={query}
                  placeholder="Scan text generation models, e.g. qwen instruct"
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && search()}
                />
                <button onClick={search}>Scan</button>
                {status._search && <span className="hint">{status._search}</span>}
              </div>
              <ul className="model-list">
                {results.map((m) => (
                  <li key={m.repo_id} className={m.suitable ? "" : "unsuitable"}>
                    <div className="model-info">
                      <div className="model-name">
                        {m.repo_id}
                        {m.params && <span className="tag">{m.params}</span>}
                        {m.downloaded && <span className="tag">on disk</span>}
                        {!m.suitable && <span className="tag warn">unsuitable</span>}
                      </div>
                      <div className="hint">
                        {m.downloads.toLocaleString()} downloads · {m.likes} likes
                        {m.reason ? ` · ${m.reason}` : ""}
                      </div>
                      {statusLine(m.repo_id)}
                    </div>
                    {m.suitable && actions(m.repo_id, m.downloaded, false)}
                  </li>
                ))}
              </ul>
            </>
          )}

          {tab === "disk" && (
            <ul className="model-list">
              {local.map((m) => (
                <li key={m.repo_id}>
                  <div className="model-info">
                    <div className="model-name">
                      {m.repo_id} <span className="tag">{formatSize(m.size_bytes)}</span>
                      {m.loaded && <span className="tag ok">loaded</span>}
                    </div>
                    {statusLine(m.repo_id)}
                  </div>
                  {actions(m.repo_id, true, m.loaded)}
                </li>
              ))}
              {local.length === 0 && <li className="hint">No models on disk yet.</li>}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
