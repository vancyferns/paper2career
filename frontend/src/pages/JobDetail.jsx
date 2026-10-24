import { useEffect, useState } from 'react';
import { getJob, listAppearances } from '../api.js';
import { fmtDate, listingStatus, cleanPhone, phoneDialUrl, UNKNOWN } from '../format.js';
import { shareJob, toggleSaved, useSaved } from '../store.js';
import { useReveal } from '../motion.js';
import AdCrop from '../components/AdCrop.jsx';
import {
  PhoneIcon, WhatsAppIcon, MailIcon, ArrowLeftIcon, HeartIcon, ShareIcon, PinIcon, CapIcon, WalletIcon, ClockIcon,
  BriefcaseIcon, ShieldIcon, PaperIcon, ExternalIcon,
} from '../components/Icons.jsx';

const waLink = (phone, job) =>
  `https://wa.me/${cleanPhone(phone)}?text=${encodeURIComponent(`Hello, I saw your job vacancy for "${job.title}" printed in ${job.newspaper} and would like to apply.`)}`;

function Section({ className = '', children }) {
  const ref = useReveal();
  return <section ref={ref} className={`card reveal ${className}`}>{children}</section>;
}

export default function JobDetail({ id }) {
  const [job, setJob] = useState(undefined);
  const [apps, setApps] = useState([]);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const saved = useSaved();

  useEffect(() => {
    Promise.all([getJob(id), listAppearances(id)])
      .then(([j, a]) => { setJob(j); setApps(a); })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (job === undefined) return <DetailSkeleton />;
  if (!job) {
    return (
      <div className="empty">
        <div className="empty-orb"><BriefcaseIcon size={26} /></div>
        <h3>Listing not available</h3>
        <p>It may still be under review.</p>
        <a className="btn primary" href="#/">Back to jobs</a>
      </div>
    );
  }

  const status = listingStatus(job);
  const latest = apps[0];
  const phones = job.contact_phones || [];
  const emails = job.contact_emails || [];
  const isSaved = saved.has(job.$id);
  const firstPhone = phones[0];

  const onShare = async () => {
    const r = await shareJob(job);
    if (r === 'copied') setToast('Link copied');
  };

  const field = (Icon, label, value) => (
    <div className="field">
      <dt><Icon size={14} /> {label}</dt>
      <dd className={value ? '' : 'unknown'}>{value || UNKNOWN}</dd>
    </div>
  );

  return (
    <article className="detail">
      <a href="#/" className="back"><ArrowLeftIcon size={16} /> All jobs</a>

      <div className="detail-grid">
        <div className="detail-main">
          <header className="detail-hero reveal in">
            <div className="job-tags">
              <span className={`pill ${status.tone}`}>{status.label}</span>
              {job.appearance_count > 1 && <span className="tag">Printed {job.appearance_count}×</span>}
            </div>
            <h1>{job.title}</h1>
            <p className="detail-employer">{job.employer || 'Employer not named'}</p>
            <ul className="facts">
              <li><PinIcon size={14} /> {job.location || 'Location not stated'}</li>
              <li><PaperIcon size={14} /> {job.newspaper} · {fmtDate(job.last_seen_at)}</li>
            </ul>
            <p className="hint">{status.hint}</p>
            <div className="detail-actions">
              <button type="button" className={`btn ${isSaved ? 'saved' : ''}`} onClick={() => toggleSaved(job.$id)} aria-pressed={isSaved}>
                <HeartIcon size={16} filled={isSaved} /> {isSaved ? 'Saved' : 'Save'}
              </button>
              <button type="button" className="btn" onClick={onShare}><ShareIcon size={16} /> Share</button>
            </div>
          </header>

          {job.has_pending_revision && (
            <div className="notice warn d-notice" role="status">
              A newer edition printed this ad with different details. A reviewer is checking the change. Until then, confirm with the advertiser.
            </div>
          )}

          <Section className="d-fields">
            <h2>From the advertisement</h2>
            <dl className="fields">
              {field(CapIcon, 'Qualification', job.qualification)}
              {field(BriefcaseIcon, 'Experience', job.experience)}
              {field(WalletIcon, 'Salary', job.salary_text)}
              {field(ClockIcon, 'Deadline', job.deadline && fmtDate(job.deadline))}
              {field(PaperIcon, 'How to apply', job.application_instructions)}
            </dl>
          </Section>

          <Section className="d-clip">
            <h2>Original clipping</h2>
            {latest ? (
              <>
                <div className="clipping"><AdCrop appearance={latest} /></div>
                <p className="muted small caption">
                  {latest.newspaper}, {fmtDate(latest.publication_date)}, page {latest.page_number}
                  {latest.section && ` · “${latest.section}”`}
                  {latest.ad_reference && ` · ref ${latest.ad_reference}`}
                  {latest.source_url && (
                    <> · <a href={latest.source_url} target="_blank" rel="noreferrer">e-paper page <ExternalIcon size={12} /></a></>
                  )}
                </p>
                <details>
                  <summary>Text as read by OCR</summary>
                  <p className="ocr">{latest.extracted_text}</p>
                </details>
              </>
            ) : <p className="muted">Source record not available.</p>}
          </Section>

          {apps.length > 0 && (
            <Section className="d-history">
              <h2>Publication history</h2>
              <ol className="timeline">
                {apps.map((a) => (
                  <li key={a.$id}>
                    <span className="when">{fmtDate(a.publication_date)}</span>
                    <span>{a.newspaper}, page {a.page_number}</span>
                    <span className="muted small">
                      {a.match_type === 'new' ? 'first appearance' : a.match_type === 'exact' ? 'identical repeat' : `matched (${a.match_type})`}
                    </span>
                    {a.source_url && <a href={a.source_url} target="_blank" rel="noreferrer" className="small">source <ExternalIcon size={11} /></a>}
                  </li>
                ))}
              </ol>
            </Section>
          )}
        </div>

        <aside className="detail-side">
          {(phones.length > 0 || emails.length > 0) && (
            <Section className="contact-card">
              <h2>Contact the employer</h2>
              <p className="muted small">Mention you saw the ad in {job.newspaper}.</p>
              <div className="contact-list">
                {phones.map((phone) => (
                  <div key={phone} className="contact-row">
                    <a href={phoneDialUrl(phone)} className="btn call"><PhoneIcon size={16} /> {phone}</a>
                    {cleanPhone(phone).length === 12 && (
                      <a href={waLink(phone, job)} target="_blank" rel="noreferrer" className="btn wa"><WhatsAppIcon size={16} /> WhatsApp</a>
                    )}
                  </div>
                ))}
                {emails.map((email) => (
                  <a
                    key={email}
                    href={`mailto:${email}?subject=${encodeURIComponent(`Application for ${job.title}`)}&body=${encodeURIComponent(`Dear Hiring Team,\n\nI am writing to apply for the ${job.title} position advertised in ${job.newspaper}.\n\nBest regards,\n`)}`}
                    className="btn mail"
                  >
                    <MailIcon size={16} /> {email}
                  </a>
                ))}
              </div>
            </Section>
          )}

          <div className="verify reveal in">
            <ShieldIcon size={20} />
            <p>
              <strong>Not independently verified.</strong> Paper2Career copies what was printed, and the newspaper does not
              authenticate advertisers either. <strong>Never pay a fee to apply.</strong>
            </p>
          </div>
        </aside>
      </div>

      {(firstPhone || emails[0]) && (
        <div className="action-bar">
          {firstPhone && <a href={phoneDialUrl(firstPhone)} className="btn call grow"><PhoneIcon size={17} /> Call</a>}
          {firstPhone && cleanPhone(firstPhone).length === 12 && (
            <a href={waLink(firstPhone, job)} target="_blank" rel="noreferrer" className="btn wa grow"><WhatsAppIcon size={17} /> WhatsApp</a>
          )}
          {!firstPhone && emails[0] && <a href={`mailto:${emails[0]}`} className="btn mail grow"><MailIcon size={17} /> Email</a>}
          <button type="button" className={`icon-btn lg ${isSaved ? 'saved' : ''}`} onClick={() => toggleSaved(job.$id)} aria-label={isSaved ? 'Remove from saved' : 'Save job'}>
            <HeartIcon size={19} filled={isSaved} />
          </button>
        </div>
      )}

      {toast && <div className="toast" role="status">{toast}</div>}
    </article>
  );
}

function DetailSkeleton() {
  return (
    <div className="detail" aria-label="Loading">
      <div className="detail-hero skeleton">
        <span className="sk sk-tag" /><span className="sk sk-title big" /><span className="sk sk-line" /><span className="sk sk-line short" />
      </div>
      <div className="card skeleton"><span className="sk sk-line" /><span className="sk sk-line" /><span className="sk sk-line short" /></div>
    </div>
  );
}
