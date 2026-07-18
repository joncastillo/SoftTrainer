// Longitudinal progress: per-metric stat tiles with sparklines and a table.

import { useEffect, useState } from "react";
import { api } from "../api";

export interface ProgressEntry {
  id: string;
  created_at: number;
  scenario: string;
  overall_score: number | null;
  filler_rate_pct: number | null;
  avg_wpm: number | null;
  eye_contact_pct: number | null;
  focus_pct: number | null;
  gaze_drift_events: number | null;
  confidence_score: number | null;
  key_points_pct: number | null;
  lost_thread_events: number | null;
}

interface MetricDef {
  key: keyof ProgressEntry;
  label: string;
  unit: string;
  // For metrics like filler rate, going down is the win.
  lowerIsBetter?: boolean;
}

const METRICS: MetricDef[] = [
  { key: "overall_score", label: "Overall score", unit: "" },
  { key: "filler_rate_pct", label: "Filler rate", unit: "%", lowerIsBetter: true },
  { key: "avg_wpm", label: "Speaking pace", unit: " wpm" },
  { key: "eye_contact_pct", label: "Eye contact", unit: "%" },
  { key: "focus_pct", label: "On-screen focus", unit: "%" },
  { key: "key_points_pct", label: "Key points covered", unit: "%" },
];

function shortDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface SeriesPoint {
  ts: number;
  value: number;
}

function Sparkline({ points, unit }: { points: SeriesPoint[]; unit: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 220;
  const H = 48;
  const PAD = 6;
  if (points.length < 2) {
    return <div className="spark-empty hint">Need more sessions for a trend.</div>;
  }
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (points.length - 1);
  const y = (v: number) => H - PAD - ((v - min) * (H - 2 * PAD)) / span;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - PAD) / (W - 2 * PAD)) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  };

  return (
    <div className="spark-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="sparkline"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Trend across sessions"
      >
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinecap="round" />
        {hover != null && (
          <>
            <line
              x1={x(hover)} x2={x(hover)} y1={PAD} y2={H - PAD}
              stroke="var(--muted)" strokeWidth={1} opacity={0.5}
            />
            <circle cx={x(hover)} cy={y(points[hover].value)} r={4}
              fill="var(--accent)" stroke="var(--panel)" strokeWidth={2} />
          </>
        )}
      </svg>
      {hover != null && (
        <div className="spark-tooltip">
          {shortDate(points[hover].ts)}: {points[hover].value}{unit}
        </div>
      )}
    </div>
  );
}

function StatTile({ metric, sessions }: { metric: MetricDef; sessions: ProgressEntry[] }) {
  const points: SeriesPoint[] = sessions
    .filter((s) => s[metric.key] != null)
    .map((s) => ({ ts: s.created_at, value: s[metric.key] as number }));
  if (points.length === 0) return null;

  const latest = points[points.length - 1].value;
  const prev = points.length > 1 ? points[points.length - 2].value : null;
  const delta = prev != null ? +(latest - prev).toFixed(1) : null;
  const improved = delta != null && (metric.lowerIsBetter ? delta < 0 : delta > 0);

  return (
    <div className="stat-tile">
      <div className="stat-label">{metric.label}</div>
      <div className="stat-value">
        {latest}
        <span className="stat-unit">{metric.unit}</span>
        {delta != null && delta !== 0 && (
          <span className={`stat-delta ${improved ? "up" : "down"}`}>
            {delta > 0 ? "+" : ""}{delta}{metric.unit} vs last
          </span>
        )}
      </div>
      <Sparkline points={points} unit={metric.unit} />
    </div>
  );
}

interface LadderSuggestion {
  text: string;
  difficulty: string;
  pressure: string;
}

export function ProgressPage() {
  const [sessions, setSessions] = useState<ProgressEntry[] | null>(null);
  const [suggestion, setSuggestion] = useState<LadderSuggestion | null>(null);

  useEffect(() => {
    api.progress().then((d) => {
      setSessions(d.sessions);
      setSuggestion(d.suggestion ?? null);
    });
  }, []);

  if (sessions === null) return <div className="page"><p className="hint">Loading...</p></div>;
  if (sessions.length === 0) {
    return (
      <div className="page">
        <h1>Progress</h1>
        <p className="hint">Finish a session or two and your trends will show up here.</p>
      </div>
    );
  }

  return (
    <div className="page progress">
      <h1>Progress</h1>
      <p className="hint">
        Trends across your {sessions.length} completed session{sessions.length === 1 ? "" : "s"},
        oldest to newest.
      </p>

      {suggestion && <div className="ladder-suggestion">{suggestion.text}</div>}

      <div className="stat-grid">
        {METRICS.map((m) => (
          <StatTile key={m.key} metric={m} sessions={sessions} />
        ))}
      </div>

      <section>
        <h3>Session by session</h3>
        <div className="table-scroll">
          <table className="progress-table">
            <thead>
              <tr>
                <th>Date</th><th>Scenario</th><th>Score</th><th>Fillers</th>
                <th>Pace</th><th>Eye contact</th><th>Focus</th>
                <th>Key points</th><th>Lost thread</th>
              </tr>
            </thead>
            <tbody>
              {[...sessions].reverse().map((s) => (
                <tr key={s.id}>
                  <td>{shortDate(s.created_at)}</td>
                  <td className="scenario-cell" title={s.scenario}>{s.scenario}</td>
                  <td>{s.overall_score ?? "—"}</td>
                  <td>{s.filler_rate_pct != null ? `${s.filler_rate_pct}%` : "—"}</td>
                  <td>{s.avg_wpm != null ? `${s.avg_wpm} wpm` : "—"}</td>
                  <td>{s.eye_contact_pct != null ? `${s.eye_contact_pct}%` : "—"}</td>
                  <td>{s.focus_pct != null ? `${s.focus_pct}%` : "—"}</td>
                  <td>{s.key_points_pct != null ? `${s.key_points_pct}%` : "—"}</td>
                  <td>{s.lost_thread_events ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
