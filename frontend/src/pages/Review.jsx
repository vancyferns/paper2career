import { useCallback, useEffect, useState } from 'react';
import {
  DEMO, acceptAllRevisions, currentReviewer, listAppearances, login, logout, publishAllJobs, publishJob, rejectJob,
  resolveRevision, reviewQueue,
} from '../api.js';
import { fmtDate } from '../format.js';
import AdCrop from '../components/AdCrop.jsx';

const EDITABLE = [
  ['title', 'Job title'], ['employer', 'Employer'], ['location', 'Location'], ['qualification', 'Qualification'],
  ['experience', 'Experience'], ['salary_text', 'Salary'], ['deadline', 'Deadline (YYYY-MM-DD)'],
  ['application_instructions', 'How to apply'],
];

export default function Review() {
  const [who, setWho] = useState(undefined);
  useEffect(() => { currentReviewer().then(setWho); }, []);

  if (who === undefined) return <p className="muted">Checking session…</p>;
  if (!who) return <Login onLogin={setWho} />;
  if (!who.demo && !who.isReviewer) {
    return (
      <div className="card narrow">
        <h1>Not a reviewer</h1>
        <p>Signed in as {who.email}, but this account isn&rsquo;t in the <code>reviewers</code> team. Ask an admin to add you in the Appwrite console.</p>
        <button onClick={() => logout().then(() => setWho(null))}>Sign out</button>
      </div>
    );
  }
  return <Queue who={who} onLogout={() => logout().then(() => setWho(null))} />;
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    try { onLogin(await login(email, password)); } catch (err) { setError(err.message); }
  };
  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>Reviewer sign in</h1>
      <label><span>Email</span><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
      <label><span>Password</span><input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" className="primary">Sign in</button>
    </form>
  );
}

function Queue({ who, onLogout }) {
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(() => reviewQueue().then(setQueue).catch((e) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  const handlePublishAll = async () => {
    if (!queue?.jobs?.length) return;
    setBusy(true);
    setError(null);
    try {
      await publishAllJobs(queue.jobs, who);
      refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleAcceptAllRevisions = async () => {
    if (!queue?.revisions?.length) return;
    setBusy(true);
    setError(null);
    try {
      await acceptAllRevisions(queue.revisions, who);
      refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="review-head">
        <h1>Review queue</h1>
        <span className="muted small">Signed in as {who.name}{DEMO && ' (demo, changes are not saved)'}</span>
        {!who.demo && <button onClick={onLogout}>Sign out</button>}
      </div>
      {queue && (queue.jobs.length > 0 || queue.revisions.length > 0) && (
        <div style={{ display: 'flex', gap: '10px', margin: '14px 0', flexWrap: 'wrap' }}>
          {queue.jobs.length > 0 && (
            <button className="primary" disabled={busy} onClick={handlePublishAll}>
              ⚡ Auto-Publish All ({queue.jobs.length})
            </button>
          )}
          {queue.revisions.length > 0 && (
            <button disabled={busy} onClick={handleAcceptAllRevisions}>
              ✓ Accept All Revisions ({queue.revisions.length})
            </button>
          )}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {!queue && !error && <p className="muted">Loading…</p>}
      {queue && (
        <>
          <h2>Changed details ({queue.revisions.length})</h2>
          {queue.revisions.length === 0 && <p className="muted">No pending revisions.</p>}
          {queue.revisions.map((r) => <RevisionItem key={r.$id} rev={r} who={who} onDone={refresh} />)}

          <h2>New extractions ({queue.jobs.length})</h2>
          {queue.jobs.length === 0 && <p className="muted">Nothing waiting for review.</p>}
          {queue.jobs.map((j) => <JobReviewItem key={j.$id} job={j} who={who} onDone={refresh} />)}
        </>
      )}
    </>
  );
}

function JobReviewItem({ job, who, onDone }) {
  const [edits, setEdits] = useState(() => Object.fromEntries(EDITABLE.map(([k]) => [k, job[k] || ''])));
  const [apps, setApps] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { listAppearances(job.$id).then(setApps); }, [job.$id]);

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try { await fn(); onDone(); } catch (e) { setError(e.message); setBusy(false); }
  };
  const cleaned = () => Object.fromEntries(Object.entries(edits).map(([k, v]) => [k, v.trim() || null]));
  const deadlineOk = !edits.deadline || /^\d{4}-\d{2}-\d{2}$/.test(edits.deadline.trim());

  return (
    <article className="card review-item">
      <div className="review-grid">
        <div>
          {apps[0] && <AdCrop appearance={apps[0]} maxHeight={360} />}
          <p className="muted small">
            {fmtDate(job.first_seen_at)}{apps[0] && `, page ${apps[0].page_number}`} · confidence {Math.round((job.confidence || 0) * 100)}%
            {apps[0] && <> · <a href={apps[0].source_url} target="_blank" rel="noreferrer">source ↗</a></>}
          </p>
          {(job.uncertain_fields || []).length > 0 && (
            <p className="flags">Check: {job.uncertain_fields.map((f) => <span key={f} className="pill warn small">{f.replaceAll('_', ' ')}</span>)}</p>
          )}
          <details open>
            <summary>OCR text</summary>
            <p className="ocr">{job.description}</p>
          </details>
        </div>
        <form className="edit-form" onSubmit={(e) => e.preventDefault()}>
          {EDITABLE.map(([k, label]) => (
            <label key={k}>
              <span>{label}</span>
              <input value={edits[k]} onChange={(e) => setEdits({ ...edits, [k]: e.target.value })}
                     placeholder="Leave blank if not stated" aria-invalid={k === 'deadline' && !deadlineOk} />
            </label>
          ))}
          <p className="muted small">Phones: {(job.contact_phones || []).join(', ') || 'none found'} · Emails: {(job.contact_emails || []).join(', ') || 'none found'}</p>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button className="primary" disabled={busy || !edits.title.trim() || !deadlineOk}
                    onClick={() => act(() => publishJob(job, cleaned(), who))}>Publish</button>
            <button disabled={busy} onClick={() => act(() => rejectJob(job, who))}>Reject (not a job / unusable)</button>
          </div>
        </form>
      </div>
    </article>
  );
}

function RevisionItem({ rev, who, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const oldV = JSON.parse(rev.old_values || '{}');
  const newV = JSON.parse(rev.new_values || '{}');
  const show = (v) => (Array.isArray(v) ? v.join(', ') : v) || '—';
  const act = async (accept) => {
    setBusy(true);
    setError(null);
    try { await resolveRevision(rev, accept, who); onDone(); } catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <article className="card review-item">
      <p>
        <a href={`#/job/${rev.job_id}`}>Job {rev.job_id}</a> reappeared on {fmtDate(rev.publication_date)}{' '}
        <span className="pill small">{rev.match_type} match{rev.match_score ? `, ${Math.round(rev.match_score)}%` : ''}</span>
      </p>
      {rev.changed_fields?.length ? (
        <table className="diff">
          <thead><tr><th scope="col">Field</th><th scope="col">Current</th><th scope="col">Newer edition</th></tr></thead>
          <tbody>
            {rev.changed_fields.map((f) => (
              <tr key={f}><th scope="row">{f.replaceAll('_', ' ')}</th><td>{show(oldV[f])}</td><td><mark>{show(newV[f])}</mark></td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">Probable repeat with no field changes. Confirm it is the same vacancy.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="primary" disabled={busy} onClick={() => act(true)}>
          {rev.changed_fields?.length ? 'Accept newer details' : 'Confirm same vacancy'}
        </button>
        <button disabled={busy} onClick={() => act(false)}>Keep current</button>
      </div>
    </article>
  );
}
