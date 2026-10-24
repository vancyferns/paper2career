import { useEffect, useMemo, useRef, useState } from 'react';
import { listPublishedJobs } from '../api.js';
import { daysBetween, fmtDate, listingStatus, cleanPhone, phoneDialUrl, today } from '../format.js';
import { CATEGORIES, matchesCategory } from '../categories.js';
import { scoreJob } from '../search.js';
import { toggleSaved, useSaved, visit } from '../store.js';
import { spotlight, useCountUp, useReveal, useRotating } from '../motion.js';
import {
  PhoneIcon, WhatsAppIcon, MailIcon, SearchIcon, SlidersIcon, XIcon, PinIcon, CapIcon, WalletIcon, HeartIcon,
  PaperIcon, BriefcaseIcon, ChevronDownIcon,
} from '../components/Icons.jsx';

const norm = (s) => (s || '').toLowerCase();
const PAGE = 24;
const ROTATING = ['hotel jobs', 'driver jobs', 'office jobs', 'teaching jobs', 'sales jobs', 'nursing jobs'];

export default function Feed({ savedOnly = false }) {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const [q, setQ] = useState('');
  const [location, setLocation] = useState('');
  const [deadline, setDeadline] = useState('any');
  const [sort, setSort] = useState('recent');
  const [dateRange, setDateRange] = useState('today');
  const [category, setCategory] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const saved = useSaved();

  useEffect(() => {
    listPublishedJobs().then(setJobs).catch((e) => setError(e.message));
  }, []);

  const latestDate = useMemo(() => {
    if (!jobs || jobs.length === 0) return today();
    return jobs.reduce((max, j) => (j.last_seen_at && j.last_seen_at > max ? j.last_seen_at : max), '');
  }, [jobs]);

  const availableDates = useMemo(() => {
    if (!jobs) return [];
    return [...new Set(jobs.map((j) => j.last_seen_at).filter(Boolean))].sort().reverse();
  }, [jobs]);

  const stats = useMemo(() => {
    if (!jobs) return { today: 0, week: 0, fresh: 0, sinceVisit: 0, towns: 0 };
    return {
      today: jobs.filter((j) => j.last_seen_at === latestDate).length,
      week: jobs.filter((j) => { const d = daysBetween(j.last_seen_at, latestDate); return d >= 0 && d <= 7; }).length,
      fresh: jobs.filter((j) => j.first_seen_at === latestDate).length,
      sinceVisit: visit.prev ? jobs.filter((j) => j.first_seen_at > visit.prev).length : 0,
      towns: new Set(jobs.map((j) => j.location).filter(Boolean)).size,
    };
  }, [jobs, latestDate]);

  const locations = useMemo(
    () => [...new Set((jobs || []).map((j) => j.location).filter(Boolean))].sort(),
    [jobs],
  );

  const activeFilterCount = [location, deadline !== 'any', sort !== 'recent', category].filter(Boolean).length;

  const resetFilters = () => {
    setLocation('');
    setDeadline('any');
    setSort('recent');
    setDateRange('today');
    setCategory('');
  };

  // Everything except the category, so the category dropdown can show counts for the current selection.
  const base = useMemo(() => {
    if (!jobs) return [];
    const t = today();
    const refDate = latestDate || t;
    const hasQuery = Boolean(q.trim());

    const scoredJobs = [];

    for (const j of jobs) {
      if (savedOnly && !saved.has(j.$id)) continue;

      let score = 0;
      if (hasQuery) {
        const res = scoreJob(j, q);
        if (!res.matches) continue;
        score = res.score;
      }

      if (location && j.location !== location) continue;
      if (deadline === 'open' && j.deadline && j.deadline < t) continue;
      if (deadline === 'has' && !j.deadline) continue;

      if (!savedOnly) {
        if (dateRange === 'today') {
          if (j.last_seen_at !== refDate) continue;
        } else if (dateRange === 'yesterday') {
          const diff = daysBetween(j.last_seen_at, refDate);
          if (diff > 1 || diff < 0) continue;
        } else if (dateRange === 'week') {
          const diff = daysBetween(j.last_seen_at, refDate);
          if (diff > 7 || diff < 0) continue;
        } else if (dateRange !== 'all') {
          if (j.last_seen_at !== dateRange) continue;
        }
      }

      scoredJobs.push({ job: j, score });
    }

    // When searching, sort by search relevance score first, then newest date
    if (hasQuery && sort === 'recent') {
      scoredJobs.sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        return (b.job.last_seen_at || '').localeCompare(a.job.last_seen_at || '');
      });
    } else {
      const key = sort === 'deadline' ? (j) => j.deadline || '9999' : (j) => j.last_seen_at || '';
      scoredJobs.sort((a, b) => (sort === 'deadline' ? key(a.job).localeCompare(key(b.job)) : key(b.job).localeCompare(key(a.job))));
    }

    return scoredJobs.map((item) => item.job);
  }, [jobs, q, location, deadline, sort, dateRange, latestDate, savedOnly, saved]);

  const categoryCounts = useMemo(
    () => Object.fromEntries(CATEGORIES.map((c) => [c.id, base.filter((j) => matchesCategory(j, c.id)).length])),
    [base],
  );

  const visible = useMemo(() => (category ? base.filter((j) => matchesCategory(j, category)) : base), [base, category]);

  useEffect(() => { setLimit(PAGE); }, [q, location, deadline, sort, dateRange, category, savedOnly]);


  return (
    <>
      {savedOnly ? (
        <section className="page-head reveal in">
          <span className="eyebrow"><HeartIcon size={13} filled /> Saved on this device</span>
          <h1>Your shortlist</h1>
          <p className="lede">Jobs you saved. Call or message before the deadline. Ads in the paper fill up quickly.</p>
        </section>
      ) : (
        <Hero jobs={jobs} latestDate={latestDate} stats={stats} />
      )}

      <div className="toolbar" id="search">
        <div className="search-row">
          <label className="search-box">
            <SearchIcon size={18} />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search role, town, qualification…"
              aria-label="Search vacancies"
              enterKeyHint="search"
            />
            {q && (
              <button type="button" className="icon-btn ghost" onClick={() => setQ('')} aria-label="Clear search"><XIcon size={16} /></button>
            )}
          </label>
          <button
            type="button"
            className={`filter-btn ${activeFilterCount > 0 ? 'active' : ''}`}
            onClick={() => setShowFilters(true)}
            aria-haspopup="dialog"
          >
            <SlidersIcon size={18} />
            <span className="hide-sm">Filters</span>
            {activeFilterCount > 0 && <span className="badge">{activeFilterCount}</span>}
          </button>
        </div>
      </div>

      {jobs && (
        <>
          <div className="pick-row">
            {!savedOnly && (
              <label className="pick">
                <PaperIcon size={15} />
                <select value={dateRange} onChange={(e) => setDateRange(e.target.value)} aria-label="Newspaper edition">
                  <option value="today">Today ({stats.today})</option>
                  <option value="yesterday">Past 2 days</option>
                  <option value="week">This week</option>
                  <option value="all">All dates</option>
                  {availableDates.length > 0 && (
                    <optgroup label="Specific edition">
                      {availableDates.map((d) => <option key={d} value={d}>{fmtDate(d)}</option>)}
                    </optgroup>
                  )}
                </select>
                <ChevronDownIcon size={15} />
              </label>
            )}
            <label className={`pick ${category ? 'on' : ''}`}>
              <BriefcaseIcon size={15} />
              <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
                <option value="">All roles</option>
                {[...CATEGORIES]
                  .filter((c) => categoryCounts[c.id] > 0 || category === c.id)
                  .sort((a, b) => (categoryCounts[b.id] || 0) - (categoryCounts[a.id] || 0))
                  .map((c) => (
                    <option key={c.id} value={c.id}>{c.label} ({categoryCounts[c.id] || 0})</option>
                ))}
              </select>
              <ChevronDownIcon size={15} />
            </label>
          </div>
          <div className="results-head" aria-live="polite">
            <p><strong>{visible.length}</strong> {visible.length === 1 ? 'job' : 'jobs'}</p>
            {(activeFilterCount > 0 || category) && (
              <button type="button" className="link-btn" onClick={resetFilters}>Clear filters</button>
            )}
          </div>
        </>
      )}

      {error && <p className="error" role="alert">Could not load listings: {error}</p>}

      {!jobs && !error && <SkeletonList />}

      <ul className="job-grid">
        {visible.slice(0, limit).map((j, i) => (
          <JobCard key={j.$id} job={j} index={i} latestDate={latestDate} saved={saved.has(j.$id)} />
        ))}
      </ul>

      {visible.length > limit && (
        <LoadMore onMore={() => setLimit((n) => n + PAGE)} left={visible.length - limit} />
      )}

      {jobs && visible.length === 0 && (
        <div className="empty reveal in">
          <div className="empty-orb">{savedOnly ? <HeartIcon size={26} /> : <SearchIcon size={26} />}</div>
          {savedOnly && saved.size === 0 ? (
            <>
              <h3>Nothing saved yet</h3>
              <p>Tap the heart on any job to keep it here.</p>
              <a className="btn primary" href="#/">Browse today’s jobs</a>
            </>
          ) : (
            <>
              <h3>No matches found</h3>
              <p>
                {dateRange !== 'all'
                  ? `No matching jobs found in this edition. Try searching across all newspaper editions.`
                  : 'Try typing a partial role, town, or keyword (e.g. "drv", "acc", "cook", "panjim").'}
              </p>
              {dateRange !== 'all' ? (
                <button type="button" className="btn primary" onClick={() => setDateRange('all')}>
                  Search all {jobs.length} newspaper jobs
                </button>
              ) : (
                <button type="button" className="btn primary" onClick={() => { setQ(''); resetFilters(); }}>
                  Reset search &amp; filters
                </button>
              )}
            </>
          )}
        </div>
      )}

      {showFilters && (
        <FilterSheet
          onClose={() => setShowFilters(false)}
          onReset={resetFilters}
          {...{ location, setLocation, deadline, setDeadline, sort, setSort, locations, category, setCategory, categoryCounts }}
        />
      )}
    </>
  );
}

// ------------------------------------------------------------------ hero

function Hero({ jobs, latestDate, stats }) {
  const word = useRotating(ROTATING);
  const marquee = useMemo(() => {
    if (!jobs) return [];
    const seen = new Set();
    return jobs.filter((j) => j.last_seen_at === latestDate && !seen.has(j.title) && seen.add(j.title)).slice(0, 18);
  }, [jobs, latestDate]);

  return (
    <section className="hero">
      <div className="hero-copy">
        <span className="eyebrow live">
          <span className="live-dot" aria-hidden="true" />
          {jobs ? `${fmtDate(latestDate)} edition is in` : 'Fetching today’s edition'}
        </span>
        <h1>
          Find <span className="rotator"><span key={word} className="grad-text">{word}</span></span>
          <br />in Goa, from this morning’s paper.
        </h1>
        <p className="lede">
          Jobs in Goa from every recruitment classified in O Heraldo, digitised daily with the original newspaper
          clipping. Call or WhatsApp the employer in one tap.
        </p>
      </div>

      <div className="stats">
        <Stat value={stats.today} label="jobs in today’s paper" accent />
        <Stat value={stats.fresh} label="printed for the first time" />
        <Stat value={stats.towns} label="towns across Goa" />
      </div>

      {stats.sinceVisit > 0 && (
        <button type="button" className="since-visit" onClick={() => document.getElementById('search')?.scrollIntoView({ behavior: 'smooth' })}>
          <span className="spark" aria-hidden="true">✦</span>
          <strong>{stats.sinceVisit} new</strong> since your last visit on {fmtDate(visit.prev)}
        </button>
      )}

      {marquee.length > 4 && (
        <div className="marquee" aria-label="Today's listings">
          <div className="marquee-track">
            {[...marquee, ...marquee].map((j, i) => (
              <a key={`${j.$id}-${i}`} href={`#/job/${j.$id}`} className="marquee-item" tabIndex={i >= marquee.length ? -1 : 0}>
                <BriefcaseIcon size={14} /> {j.title}{j.location ? <span className="muted"> · {j.location}</span> : null}
              </a>
            ))}
          </div>
        </div>
      )}

    </section>
  );
}

function Stat({ value, label, accent }) {
  const n = useCountUp(value);
  return (
    <div className={`stat ${accent ? 'accent' : ''}`}>
      <span className="stat-n">{n}</span>
      <span className="stat-l">{label}</span>
    </div>
  );
}

// ------------------------------------------------------------------ cards

function JobCard({ job, index, latestDate, saved }) {
  const ref = useReveal();
  const status = listingStatus(job);
  const phones = job.contact_phones || [];
  const emails = job.contact_emails || [];
  const isNew = job.first_seen_at === latestDate;
  const sinceVisit = visit.prev && job.first_seen_at > visit.prev;

  return (
    <li ref={ref} className="job-card reveal" style={{ '--d': `${(index % 4) * 70}ms` }} onPointerMove={spotlight}>
      <a href={`#/job/${job.$id}`} className="job-link">
        <div className="job-tags">
          {isNew ? <span className="tag new">New today</span>
            : job.appearance_count > 1 ? <span className="tag">Printed {job.appearance_count}×</span> : null}
          {sinceVisit && !isNew && <span className="tag new">New for you</span>}
          <span className={`pill ${status.tone}`} title={status.hint}>{status.label}</span>
          {job.has_pending_revision && <span className="pill warn">Details updated</span>}
        </div>
        <h2>{job.title}</h2>
        <p className="job-employer">{job.employer || <span className="muted">Employer not named</span>}</p>
        {(job.location || job.qualification || job.salary_text) && (
          <ul className="facts">
            {job.location && <li><PinIcon size={14} /> {job.location}</li>}
            {job.qualification && <li><CapIcon size={14} /> {job.qualification}</li>}
            {job.salary_text && <li className="salary"><WalletIcon size={14} /> {job.salary_text}</li>}
          </ul>
        )}
        <p className="job-source"><PaperIcon size={13} /> {job.newspaper} · {fmtDate(job.last_seen_at)}</p>
      </a>

      <button
        type="button"
        className={`save-btn ${saved ? 'on' : ''}`}
        onClick={() => toggleSaved(job.$id)}
        aria-pressed={saved}
        aria-label={saved ? 'Remove from saved' : 'Save job'}
      >
        <HeartIcon size={18} filled={saved} />
      </button>

      {(phones.length > 0 || emails.length > 0) && (
        <div className="quick-actions">
          {phones.slice(0, 1).map((phone) => {
            const clean = cleanPhone(phone);
            return (
              <span key={phone} className="qa-group">
                <a href={phoneDialUrl(phone)} className="qa call" aria-label={`Call ${phone}`}><PhoneIcon size={15} /> Call</a>
                {clean.length === 12 && (
                  <a
                    href={`https://wa.me/${clean}?text=${encodeURIComponent(`Hi, I saw your vacancy for "${job.title}" in ${job.newspaper}.`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="qa wa"
                  >
                    <WhatsAppIcon size={15} /> WhatsApp
                  </a>
                )}
              </span>
            );
          })}
          {emails.slice(0, 1).map((email) => (
            <a key={email} href={`mailto:${email}?subject=${encodeURIComponent(`Application: ${job.title}`)}`}
               className="qa mail" aria-label={`Email ${email}`}>
              <MailIcon size={15} /> Email
            </a>
          ))}
          {phones.length > 1 && <a href={`#/job/${job.$id}`} className="qa more">+{phones.length - 1}</a>}
        </div>
      )}
    </li>
  );
}

function LoadMore({ onMore, left }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !('IntersectionObserver' in window)) return undefined;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && onMore(), { rootMargin: '400px' });
    io.observe(el);
    return () => io.disconnect();
  }, [onMore]);
  return (
    <div ref={ref} className="load-more">
      <button type="button" className="btn" onClick={onMore}>Show more · {left} left</button>
    </div>
  );
}

function SkeletonList() {
  return (
    <ul className="job-grid" aria-label="Loading listings">
      {Array.from({ length: 6 }, (_, i) => (
        <li key={i} className="job-card skeleton">
          <span className="sk sk-tag" /><span className="sk sk-title" /><span className="sk sk-line" /><span className="sk sk-line short" />
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ filters

function Segmented({ value, onChange, options }) {
  return (
    <div className="segmented" role="radiogroup">
      {options.map(([v, label]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v}
                className={value === v ? 'active' : ''} onClick={() => onChange(v)}>{label}</button>
      ))}
    </div>
  );
}

function FilterSheet({
  onClose, onReset, location, setLocation, deadline, setDeadline, sort, setSort, locations, category, setCategory, categoryCounts,
}) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    document.body.classList.add('lock');
    return () => { document.removeEventListener('keydown', onKey); document.body.classList.remove('lock'); };
  }, [onClose]);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Filters" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grip" aria-hidden="true" />
        <div className="sheet-head">
          <h2>Filters</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close filters"><XIcon size={18} /></button>
        </div>

        <div className="sheet-body">
          <label className="field-label">
            <span>Job Role</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All roles</option>
              {[...CATEGORIES]
                .filter((c) => (categoryCounts && categoryCounts[c.id] > 0) || category === c.id)
                .sort((a, b) => ((categoryCounts && categoryCounts[b.id]) || 0) - ((categoryCounts && categoryCounts[a.id]) || 0))
                .map((c) => (
                  <option key={c.id} value={c.id}>{c.label} ({(categoryCounts && categoryCounts[c.id]) || 0})</option>
              ))}
            </select>
          </label>

          <label className="field-label">
            <span>Location</span>
            <select value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">Anywhere in Goa</option>
              {locations.map((l) => <option key={l}>{l}</option>)}
            </select>
          </label>

          <div className="field-label">
            <span>Application deadline</span>
            <Segmented value={deadline} onChange={setDeadline}
                       options={[['any', 'Any'], ['open', 'Not passed'], ['has', 'Has deadline']]} />
          </div>

          <div className="field-label">
            <span>Sort by</span>
            <Segmented value={sort} onChange={setSort}
                       options={[['recent', 'Latest printed'], ['deadline', 'Closing soonest']]} />
          </div>
        </div>

        <div className="sheet-foot">
          <button type="button" className="btn ghost" onClick={onReset}>Reset</button>
          <button type="button" className="btn primary grow" onClick={onClose}>Show results</button>
        </div>
      </div>
    </div>
  );
}
