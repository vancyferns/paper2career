import { useEffect, useState } from 'react';
import { listRuns } from '../api.js';
import { PulseIcon } from '../components/Icons.jsx';

const TONE = { SUCCESS: 'ok', NO_NEW_EDITION: 'neutral', PARTIAL: 'warn', FAILED: 'bad', RUNNING: 'neutral' };

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export default function Runs() {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { listRuns().then(setRuns).catch((e) => setError(e.message)); }, []);

  return (
    <>
      <section className="page-head reveal in">
        <span className="eyebrow"><PulseIcon size={13} /> System status</span>
        <h1>Ingestion runs</h1>
        <p className="lede">
          The worker checks the e-paper every morning and retries later in the day, because the edition may be published
          after the first run. A run that finds nothing new is logged as <em>NO_NEW_EDITION</em>, not as success.
        </p>
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      {!runs && !error && <p className="muted">Loading…</p>}
      {runs && runs.length === 0 && <div className="empty"><p>No runs recorded yet.</p></div>}
      {runs && runs.length > 0 && (
        <ul className="runs">
          {runs.map((r) => (
            <li key={r.$id} className="card run">
              <div className="run-head">
                <span className={`pill ${TONE[r.status] || 'neutral'}`}>{r.status}</span>
                <span className="muted small">{fmtTime(r.started_at)}{r.trigger ? ` · ${r.trigger}` : ''}</span>
              </div>
              <dl className="run-stats">
                <div><dt>Editions</dt><dd>{r.editions_processed ?? 0}/{r.editions_found ?? 0}</dd></div>
                <div><dt>Pages</dt><dd>{r.pages_processed ?? 0}{r.pages_failed ? <small> ({r.pages_failed} failed)</small> : ''}</dd></div>
                <div><dt>Extracted</dt><dd>{r.jobs_extracted ?? 0}</dd></div>
                <div><dt>New</dt><dd className="hi">{r.new_jobs ?? 0}</dd></div>
                <div><dt>Repeats</dt><dd>{r.repeat_appearances ?? 0}</dd></div>
                <div><dt>Flagged</dt><dd>{r.revisions_flagged ?? 0}</dd></div>
              </dl>
              {(r.error_message || r.notes) && <p className="muted small run-note">{r.error_message || r.notes}</p>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
