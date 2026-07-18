// Backend discovery. The backend increments its port when 8000 is
// taken, so the app probes: same origin first (production build or the
// vite proxy), then localhost ports 8000 to 8019 directly.

const PORT_START = 8000;
const PORT_END = 8020;

let resolved: string | null = null;
let resolving: Promise<string> | null = null;

async function probe(origin: string): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1200);
  try {
    const r = await fetch(`${origin}/api/health`, { signal: ctrl.signal });
    return r.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function locate(): Promise<string> {
  if (await probe("")) return "";
  const host = location.hostname || "localhost";
  for (let port = PORT_START; port < PORT_END; port++) {
    const origin = `http://${host}:${port}`;
    if (await probe(origin)) return origin;
  }
  throw new Error(
    `Could not reach the SoftTrainer backend on ports ${PORT_START}-${PORT_END - 1}. Is it running?`,
  );
}

export async function backendBase(): Promise<string> {
  if (resolved !== null) return resolved;
  resolving ??= locate()
    .then((origin) => (resolved = origin))
    .finally(() => (resolving = null));
  return resolving;
}

export async function backendWsBase(): Promise<string> {
  const base = await backendBase();
  return (base || location.origin).replace(/^http/, "ws");
}
