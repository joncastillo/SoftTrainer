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
            {report.behavior.focus_pct != null && (
              <li>
                On-screen focus: {report.behavior.focus_pct}%
                {(report.behavior.gaze_drift_events ?? 0) > 0 &&
                  ` (drifted away ${report.behavior.gaze_drift_events} time${
                    report.behavior.gaze_drift_events === 1 ? "" : "s"})`}
              </li>
            )}
          </ul>
        </section>
      )}

      {report.delivery?.available && (
        <section>
          <h3>Delivery metrics</h3>
          <ul>
            <li>Filler words: {report.delivery.filler_count} ({report.delivery.filler_rate_pct}% of words)</li>
            {report.delivery.avg_wpm != null && <li>Speaking pace: {report.delivery.avg_wpm} words/min</li>}
            <li>Words spoken: {report.delivery.total_words} across {report.delivery.utterances} turns</li>
          </ul>
        </section>
      )}

      {report.key_points?.available && (
        <section>
          <h3>Key points</h3>
          <p className="hint">
            Covered {report.key_points.covered_count} of {report.key_points.total}
            {(report.key_points.lost_thread_events ?? 0) > 0 &&
              ` · lost the thread ${report.key_points.lost_thread_events} time${
                report.key_points.lost_thread_events === 1 ? "" : "s"}`}
          </p>
          <ul className="keypoint-list static">
            {report.key_points.points?.map((p) => (
              <li key={p.text} className={p.covered ? "covered" : "missed"}>
                <span className="keypoint-mark">{p.covered ? "✓" : "✗"}</span>
                {p.text}
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.composure?.available && (
        <section>
          <h3>Composure under pressure</h3>
          <p className="hint">
            {report.composure.events} heckle/distraction event
            {report.composure.events === 1 ? "" : "s"} at {report.composure.level} pressure
          </p>
          <ul>
            {report.composure.filler_rate_under_pressure_pct != null && (
              <li>
                Filler rate: {report.composure.filler_rate_baseline_pct}% baseline →{" "}
                {report.composure.filler_rate_under_pressure_pct}% under pressure
              </li>
            )}
            {report.composure.eye_contact_under_pressure_pct != null && (
              <li>
                Eye contact: {report.composure.eye_contact_baseline_pct}% baseline →{" "}
                {report.composure.eye_contact_under_pressure_pct}% under pressure
              </li>
            )}
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

      <p className="hint disclaimer">
        SoftTrainer is a practice tool, not a medical or therapeutic device. Scores
        are rough coaching signals — trust your own sense of progress over any number.
      </p>
    </div>
  );
}
