import { useEffect, useState } from 'react';
import { getJob, listAppearances } from '../api.js';
import { fmtDate, listingStatus, UNKNOWN } from '../format.js';
import AdCrop from '../components/AdCrop.jsx';

export default function JobDetail({ id }) {
  const [job, setJob] = useState(undefined);
  const [apps, setApps] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getJob(id), listAppearances(id)])
      .then(([j, a]) => { setJob(j); setApps(a); })
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (job === undefined) return <p className="muted">Loading…</p>;
  if (!job) return <p className="empty">This listing is not available. It may still be under review. <a href="#/">Back to jobs</a></p>;

  const status = listingStatus(job);
  const latest = apps[0];
  const field = (label, value) => (
    <div className="field">
      <dt>{label}</dt>
      <dd className={value ? '' : 'unknown'}>{value || UNKNOWN}</dd>
    </div>
  );

  return (
    <article className="detail">
      <a href="#/" className="back">← All jobs</a>
      <header className="detail-head">
        <h1>{job.title}</h1>
        <p className="job-meta">{job.employer || 'Employer not named'} · {job.location || 'Location not stated'}</p>
        <span className={`pill ${status.tone}`}>{status.label}</span>
        <p className="muted small">{status.hint}</p>
      </header>

      {job.has_pending_revision && (
        <div className="notice warn" role="status">
          A newer edition printed this ad with different details. A reviewer is checking the change. Until then, confirm with the advertiser.
        </div>
      )}

      <section className="card">
        <h2>Details from the advertisement</h2>
        <dl className="fields">
          {field('Qualification', job.qualification)}
          {field('Experience', job.experience)}
          {field('Salary', job.salary_text)}
          {field('Deadline', job.deadline && fmtDate(job.deadline))}
          {field('Phone', (job.contact_phones || []).join(', '))}
          {field('Email', (job.contact_emails || []).join(', '))}
          {field('How to apply', job.application_instructions)}
        </dl>
        <p className="verify">
          <strong>Not independently verified.</strong> Paper2Career copies what was printed. The newspaper does not
          authenticate advertisers either. Never pay a fee to apply.
        </p>
      </section>

      <section className="card">
        <h2>Original advertisement</h2>
        {latest ? (
          <>
            <AdCrop appearance={latest} />
            <p className="muted small">
              {latest.newspaper}, {fmtDate(latest.publication_date)}, page {latest.page_number}
              {latest.section && ` · section “${latest.section}”`}
              {latest.ad_reference && ` · ad ref ${latest.ad_reference}`} ·{' '}
              <a href={latest.source_url} target="_blank" rel="noreferrer">view the e-paper page ↗</a>
            </p>
            <details>
              <summary>Text as read by OCR</summary>
              <p className="ocr">{latest.extracted_text}</p>
            </details>
          </>
        ) : <p className="muted">Source record not available.</p>}
      </section>

      <section className="card">
        <h2>Publication history</h2>
        <ol className="history">
          {apps.map((a) => (
            <li key={a.$id}>
              <span className="when">{fmtDate(a.publication_date)}</span>
              <span>{a.newspaper}, page {a.page_number}</span>
              <span className="muted small">
                {a.match_type === 'new' ? 'first appearance' : a.match_type === 'exact' ? 'identical repeat' : `matched (${a.match_type})`}
              </span>
              <a href={a.source_url} target="_blank" rel="noreferrer">source ↗</a>
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}
