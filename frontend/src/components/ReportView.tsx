import type { Report } from "../types";

export function ReportView({ report }: { report: Report }) {
  return (
    <div className="report">
      <div className="report-header">
        <h2>Assessment</h2>
        {report.overall_score != null && (
          <div className="score-badge">{Math.round(report.overall_score)}</div>
        )}
      </div>
      <p className="report-summary">{report.summary}</p>

      {report.dimensions?.length > 0 && (
        <section>
          <h3>Dimensions</h3>
          {report.dimensions.map((d) => (
            <div key={d.name} className="dimension">
              <div className="dimension-label">
                <span>{d.name}</span>
                <span>{d.score}</span>
              </div>
              <div className="bar">
                <div className="bar-fill" style={{ width: `${Math.min(100, d.score)}%` }} />
              </div>
              <p className="dimension-comment">{d.comment}</p>
            </div>
          ))}
        </section>
      )}

      {report.behavior?.available && (
        <section>
          <h3>Presence metrics</h3>
          <ul>
            <li>Eye contact: {report.behavior.eye_contact_pct}%</li>
            <li>Head stability: {report.behavior.head_stability}</li>
            <li>Camera confidence score: {report.behavior.confidence_score}</li>
            <li>Face visible: {report.behavior.face_visible_pct}% of frames</li>
          </ul>
        </section>
      )}

      {report.strengths?.length > 0 && (
        <section>
          <h3>Strengths</h3>
          <ul>{report.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </section>
      )}

      {report.improvements?.length > 0 && (
        <section>
          <h3>Improvements</h3>
          <ul>{report.improvements.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </section>
      )}

      {report.notable_moments?.length > 0 && (
        <section>
          <h3>Notable moments</h3>
          {report.notable_moments.map((m, i) => (
            <blockquote key={i}>
              "{m.quote}"
              <footer>{m.comment}</footer>
            </blockquote>
          ))}
        </section>
      )}
    </div>
  );
}
