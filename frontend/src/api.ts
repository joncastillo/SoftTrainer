// Thin fetch wrappers around the backend REST API.

import { backendBase } from "./backend";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const base = await backendBase();
  const r = await fetch(base + url, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return r.json();
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<any>("/api/health"),

  createSession: (body: unknown) => request<{ id: string }>("/api/sessions", json(body)),
  listSessions: () => request<any[]>("/api/sessions"),
  progress: () => request<any>("/api/progress"),
  saveReflection: (id: string, answers: unknown[]) =>
    request<any>(`/api/sessions/${id}/reflection`, json({ answers })),
  getSession: (id: string) => request<any>(`/api/sessions/${id}`),

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<any>("/api/documents", { method: "POST", body: form });
  },
  listDocuments: () => request<any[]>("/api/documents"),
  deleteDocument: (id: string) => request<any>(`/api/documents/${id}`, { method: "DELETE" }),

  listProviders: () => request<any[]>("/api/providers"),
  saveProvider: (p: unknown) => request<any>("/api/providers", json(p)),
  deleteProvider: (id: string) => request<any>(`/api/providers/${id}`, { method: "DELETE" }),
  activateProvider: (id: string) => request<any>(`/api/providers/${id}/activate`, { method: "POST" }),
  testProvider: (id: string) => request<any>(`/api/providers/${id}/test`, { method: "POST" }),

  recommendedModels: () => request<any[]>("/api/models/recommended"),
  searchModels: (q: string) => request<any[]>(`/api/models/search?q=${encodeURIComponent(q)}`),
  localModels: () => request<any[]>("/api/models/local"),
  downloadModel: (repo_id: string) => request<any>("/api/models/download", json({ repo_id })),
  downloadStatus: (repo_id: string) =>
    request<any>(`/api/models/download-status?repo_id=${encodeURIComponent(repo_id)}`),
  loadModel: (repo_id: string) => request<any>("/api/models/load", json({ repo_id })),
  loadStatus: (repo_id: string) =>
    request<any>(`/api/models/load-status?repo_id=${encodeURIComponent(repo_id)}`),
  unloadModel: (repo_id: string) => request<any>("/api/models/unload", json({ repo_id })),
  deleteModel: (repo_id: string) => request<any>(`/api/models/${repo_id}`, { method: "DELETE" }),
};
