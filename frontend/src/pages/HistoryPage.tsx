// Saved sessions browser: transcripts and reports from disk.

import { useEffect, useState } from "react";
import { api } from "../api";
import { Markdown } from "../components/Markdown";
import { ReportView } from "../components/ReportView";
import type { Report, SessionMeta, TranscriptEntry } from "../types";

export function HistoryPage() {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    transcript: TranscriptEntry[];
    report: Report | null;
    reflection: { question: string; answer: string }[] | null;
  } | null>(null);
  const [tab, setTab] = useState<"report" | "transcript">("report");

  useEffect(() => {
    api.listSessions().then(setSessions);
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    api.getSession(selected).then((d) =>
      setDetail({
        transcript: d.transcript,
        report: d.report,
        reflection: d.meta?.reflection ?? null,
      }),
    );
  }, [selected]);

  return (
    <div className="page history">
      <h1>Past sessions</h1>
      <div className="history-layout">
        <ul className="session-list">
          {sessions.map((s) => (
            <li
              key={s.id}
              className={selected === s.id ? "active" : ""}
              onClick={() => setSelected(s.id)}
            >
              <div className="session-scenario">{s.scenario}</div>
              <div className="session-sub">
                {new Date(s.created_at * 1000).toLocaleString()} · {s.status}
                {s.has_report ? " · report ready" : ""}
              </div>
            </li>
          ))}
          {sessions.length === 0 && <li className="hint">No sessions yet.</li>}
        </ul>

        <div className="history-detail">
          {selected && !detail && <p className="hint">Loading...</p>}
          {detail && (
            <>
              <div className="tabs">
                <button className={tab === "report" ? "active" : ""} onClick={() => setTab("report")}>
                  Report
                </button>
                <button
                  className={tab === "transcript" ? "active" : ""}
                  onClick={() => setTab("transcript")}
                >
                  Transcript
                </button>
              </div>
              {tab === "report" && (
                <>
                  {detail.report ? (
                    <ReportView report={detail.report} />
                  ) : (
                    <p className="hint">No report was generated for this session.</p>
                  )}
                  {detail.reflection && detail.reflection.length > 0 && (
                    <section className="reflection-card">
                      <h3>Your reflection</h3>
                      {detail.reflection.map((r) => (
                        <p key={r.question}>
                          <span className="hint">{r.question}</span>
                          <br />
                          {r.answer}
                        </p>
                      ))}
                    </section>
                  )}
                </>
              )}
              {tab === "transcript" && (
                <div className="conversation static">
                  {detail.transcript.map((t, i) => (
                    <div key={i} className={`bubble ${t.role}`}>
                      {t.role === "assistant" ? <Markdown text={t.text} /> : t.text}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
