import { useEffect, useState } from 'react';
import { listRuns } from '../api.js';

const TONE = { SUCCESS: 'ok', NO_NEW_EDITION: 'neutral', PARTIAL: 'warn', FAILED: 'bad', RUNNING: 'neutral' };

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export default function Runs() {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { listRuns().then(setRuns).catch((e) => setError(e.message)); }, []);

  return (
    <>
      <h1>Ingestion status</h1>
      <p className="muted">
        The worker checks the e-paper every morning and retries later in the day, because the edition may be published
        after the first run. A run that finds nothing new is logged as <em>NO_NEW_EDITION</em>, not as success.
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      {!runs && !error && <p className="muted">Loading…</p>}
      {runs && runs.length === 0 && <p className="empty">No runs recorded yet.</p>}
      {runs && runs.length > 0 && (
        <div className="table-scroll">
          <table className="runs">
            <thead>
              <tr>
                <th scope="col">Started</th><th scope="col">Status</th><th scope="col">Trigger</th>
                <th scope="col">Editions</th><th scope="col">Pages</th><th scope="col">Jobs extracted</th>
                <th scope="col">New</th><th scope="col">Repeats</th><th scope="col">Flagged</th><th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.$id}>
                  <td>{fmtTime(r.started_at)}</td>
                  <td><span className={`pill ${TONE[r.status] || 'neutral'}`}>{r.status}</span></td>
                  <td>{r.trigger || '—'}</td>
                  <td>{r.editions_processed ?? 0}/{r.editions_found ?? 0}</td>
                  <td>{r.pages_processed ?? 0}{r.pages_failed ? ` (${r.pages_failed} failed)` : ''}</td>
                  <td>{r.jobs_extracted ?? 0}</td>
                  <td>{r.new_jobs ?? 0}</td>
                  <td>{r.repeat_appearances ?? 0}</td>
                  <td>{r.revisions_flagged ?? 0}</td>
                  <td className="small">{r.error_message || r.notes || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
