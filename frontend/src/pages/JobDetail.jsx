import { useEffect, useState } from 'react';
import { getJob, listAppearances } from '../api.js';
import { fmtDate, listingStatus, cleanPhone, phoneDialUrl, UNKNOWN } from '../format.js';
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

      {((job.contact_phones && job.contact_phones.length > 0) || (job.contact_emails && job.contact_emails.length > 0)) && (
        <section className="card contact-action-card">
          <h2>Direct Contact & Application</h2>
          <p className="contact-action-hint">Reach out to this employer directly via phone, WhatsApp, or email:</p>
          <div className="contact-btn-row">
            {job.contact_phones?.map((phone) => {
              const clean = cleanPhone(phone);
              return (
                <div key={phone} className="phone-btn-group">
                  <a href={phoneDialUrl(phone)} className="btn-direct btn-direct-call">
                    ?? Call {phone}
                  </a>
                  {clean.length === 12 && (
                    <a
                      href={`https://wa.me/${clean}?text=${encodeURIComponent(`Hello, I saw your job vacancy for "${job.title}" printed in ${job.newspaper} and would like to apply.`)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-direct btn-direct-wa"
                    >
                      ?? WhatsApp
                    </a>
                  )}
                </div>
              );
            })}
            {job.contact_emails?.map((email) => (
              <a
                key={email}
                href={`mailto:${email}?subject=${encodeURIComponent(`Application for ${job.title}`)}&body=${encodeURIComponent(`Dear Hiring Team,\n\nI am writing to apply for the ${job.title} position advertised in ${job.newspaper}.\n\nBest regards,\n`)}`}
                className="btn-direct btn-direct-email"
              >
                ?? Email ({email})
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <h2>Details from the advertisement</h2>
        <dl className="fields">
          {field('Qualification', job.qualification)}
          {field('Experience', job.experience)}
          {field('Salary', job.salary_text)}
          {field('Deadline', job.deadline && fmtDate(job.deadline))}
          {field('Phone', (job.contact_phones || []).length > 0 ? (
            <span className="field-links">
              {job.contact_phones.map((p) => (
                <a key={p} href={phoneDialUrl(p)} className="field-click-link">?? {p}</a>
              ))}
            </span>
          ) : null)}
          {field('Email', (job.contact_emails || []).length > 0 ? (
            <span className="field-links">
              {job.contact_emails.map((e) => (
                <a key={e} href={`mailto:${e}`} className="field-click-link">?? {e}</a>
              ))}
            </span>
          ) : null)}
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
