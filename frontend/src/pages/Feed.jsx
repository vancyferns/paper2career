import { useEffect, useMemo, useState } from 'react';
import { listPublishedJobs } from '../api.js';
import { daysBetween, fmtDate, listingStatus, today } from '../format.js';

const norm = (s) => (s || '').toLowerCase();

export default function Feed() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const [q, setQ] = useState('');
  const [location, setLocation] = useState('');
  const [deadline, setDeadline] = useState('any');
  const [sort, setSort] = useState('recent');
  const [dateRange, setDateRange] = useState('today');
  const [showFilters, setShowFilters] = useState(false);

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

  const todayCount = useMemo(() => {
    if (!jobs || !latestDate) return 0;
    return jobs.filter((j) => j.last_seen_at === latestDate).length;
  }, [jobs, latestDate]);

  const weekCount = useMemo(() => {
    if (!jobs || !latestDate) return 0;
    return jobs.filter((j) => {
      const d = daysBetween(j.last_seen_at, latestDate);
      return d >= 0 && d <= 7;
    }).length;
  }, [jobs, latestDate]);

  const locations = useMemo(
    () => [...new Set((jobs || []).map((j) => j.location).filter(Boolean))].sort(),
    [jobs],
  );

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (location) count++;
    if (deadline !== 'any') count++;
    if (sort !== 'recent') count++;
    if (dateRange !== 'today') count++;
    return count;
  }, [location, deadline, sort, dateRange]);

  const visible = useMemo(() => {
    if (!jobs) return [];
    const terms = norm(q).split(/\s+/).filter(Boolean);
    const t = today();
    const refDate = latestDate || t;
    const out = jobs.filter((j) => {
      const hay = norm([j.title, j.employer, j.location, j.qualification, j.experience, j.description].join(' '));
      if (!terms.every((term) => hay.includes(term))) return false;
      if (location && j.location !== location) return false;
      if (deadline === 'open' && j.deadline && j.deadline < t) return false;
      if (deadline === 'has' && !j.deadline) return false;

      // Date range filtering
      if (dateRange === 'today') {
        if (j.last_seen_at !== refDate) return false;
      } else if (dateRange === 'yesterday') {
        const diff = daysBetween(j.last_seen_at, refDate);
        if (diff > 1 || diff < 0) return false;
      } else if (dateRange === 'week') {
        const diff = daysBetween(j.last_seen_at, refDate);
        if (diff > 7 || diff < 0) return false;
      } else if (dateRange !== 'all') {
        if (j.last_seen_at !== dateRange) return false;
      }

      return true;
    });
    const key = sort === 'deadline' ? (j) => j.deadline || '9999' : (j) => j.last_seen_at;
    out.sort((a, b) => (sort === 'deadline' ? key(a).localeCompare(key(b)) : key(b).localeCompare(key(a))));
    return out;
  }, [jobs, q, location, deadline, sort, dateRange, latestDate]);

  return (
    <>
      <section className="hero">
        <div className="hero-header">
          <h1>
            {dateRange === 'today' && latestDate ? "Today's Newspaper Jobs" : 'Newspaper Classified Jobs'}
          </h1>
          {dateRange === 'today' && latestDate && (
            <span className="hero-date-badge">🗞️ {fmtDate(latestDate)} edition</span>
          )}
        </div>
        <p>Recruitment ads from O Heraldo, digitised daily with source newspaper clipping.</p>
      </section>

      {/* Main Search & Filter Control Bar */}
      <div className="search-filter-box">
        <div className="search-row">
          <div className="search-input-wrap">
            <span className="search-icon" aria-hidden="true">🔍</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search role, town, qualification…"
              aria-label="Search vacancies"
            />
            {q && (
              <button type="button" className="btn-clear" onClick={() => setQ('')} aria-label="Clear search">✕</button>
            )}
          </div>
          <button
            type="button"
            className={`btn-filter-toggle ${showFilters || activeFilterCount > 0 ? 'active' : ''}`}
            onClick={() => setShowFilters(!showFilters)}
            aria-expanded={showFilters}
          >
            <span>Filters</span>
            {activeFilterCount > 0 && <span className="pill-badge">{activeFilterCount}</span>}
            <span className="toggle-arrow">{showFilters ? '▲' : '▼'}</span>
          </button>
        </div>

        {/* Date Tabs (Horizontal Swipeable Bar) */}
        <div className="date-tabs" role="tablist" aria-label="Filter by edition date">
          <button
            type="button"
            className={`tab-btn ${dateRange === 'today' ? 'active' : ''}`}
            onClick={() => setDateRange('today')}
          >
            🗞️ Today&rsquo;s Paper {todayCount > 0 ? `(${todayCount})` : ''}
          </button>
          <button
            type="button"
            className={`tab-btn ${dateRange === 'yesterday' ? 'active' : ''}`}
            onClick={() => setDateRange('yesterday')}
          >
            Past 2 Days
          </button>
          <button
            type="button"
            className={`tab-btn ${dateRange === 'week' ? 'active' : ''}`}
            onClick={() => setDateRange('week')}
          >
            Past Week {weekCount > 0 ? `(${weekCount})` : ''}
          </button>

          <button
            type="button"
            className={`tab-btn ${dateRange === 'all' ? 'active' : ''}`}
            onClick={() => setDateRange('all')}
          >
            All Available {jobs ? `(${jobs.length})` : ''}
          </button>
        </div>

        {/* Expandable Filter Drawer */}
        {showFilters && (
          <div className="filters-panel">
            <div className="filters-grid">
              <label>
                <span>Newspaper Edition</span>
                <select value={dateRange} onChange={(e) => setDateRange(e.target.value)}>
                  <option value="today">Today&rsquo;s Edition ({latestDate ? fmtDate(latestDate) : 'Latest'})</option>
                  <option value="yesterday">Past 2 Days (Yesterday & Today)</option>
                  <option value="week">Past Week (Last 7 Days)</option>

                  <option value="all">All Dates ({jobs?.length || 0})</option>
                  {availableDates.length > 0 && (
                    <optgroup label="Specific Edition Date">
                      {availableDates.map((d) => (
                        <option key={d} value={d}>
                          {fmtDate(d)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </label>

              <label>
                <span>Location</span>
                <select value={location} onChange={(e) => setLocation(e.target.value)}>
                  <option value="">Anywhere in Goa</option>
                  {locations.map((l) => <option key={l}>{l}</option>)}
                </select>
              </label>

              <label>
                <span>Application Deadline</span>
                <select value={deadline} onChange={(e) => setDeadline(e.target.value)}>
                  <option value="any">Any deadline</option>
                  <option value="open">Not yet passed</option>
                  <option value="has">Has a deadline</option>
                </select>
              </label>

              <label>
                <span>Sort Order</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)}>
                  <option value="recent">Most recently printed</option>
                  <option value="deadline">Closing soonest</option>
                </select>
              </label>
            </div>

            <div className="filters-footer">
              <button
                type="button"
                className="btn-reset"
                onClick={() => {
                  setLocation('');
                  setDeadline('any');
                  setSort('recent');
                  setDateRange('today');
                }}
              >
                Reset all filters
              </button>
              <button type="button" className="btn-done" onClick={() => setShowFilters(false)}>
                Done
              </button>
            </div>
          </div>
        )}
      </div>

      {error && <p className="error" role="alert">Could not load listings: {error}</p>}
      {!jobs && !error && <p className="muted">Loading listings…</p>}
      {jobs && (
        <div className="results-head">
          <p className="muted count" aria-live="polite">
            Showing <strong>{visible.length}</strong> of {jobs.length} vacancies
            {dateRange === 'today' && latestDate && ` · Today's paper (${fmtDate(latestDate)})`}
            {dateRange === 'yesterday' && ' · Past 2 days'}
            {dateRange === 'week' && ' · Past 7 days'}
            {dateRange === 'month' && ' · Past 30 days'}
            {dateRange !== 'today' && dateRange !== 'yesterday' && dateRange !== 'week' && dateRange !== 'month' && dateRange !== 'all' && ` · ${fmtDate(dateRange)}`}
          </p>
          {activeFilterCount > 0 && (
            <button
              type="button"
              className="btn-clear-filters"
              onClick={() => {
                setLocation('');
                setDeadline('any');
                setSort('recent');
                setDateRange('today');
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      <ul className="job-list">
        {visible.map((j) => <JobCard key={j.$id} job={j} />)}
      </ul>
      {jobs && visible.length === 0 && (
        <div className="empty">
          <p>No listings found matching the selected filters.</p>
          <button type="button" className="btn-done" style={{ marginTop: '0.5rem' }} onClick={() => {
            setQ('');
            setLocation('');
            setDeadline('any');
            setDateRange('all');
          }}>
            Show all {jobs.length} jobs
          </button>
        </div>
      )}
    </>
  );
}

function JobCard({ job }) {
  const status = listingStatus(job);
  return (
    <li className="card job-card">
      <a href={`#/job/${job.$id}`} className="job-link">
        <div className="job-head">
          <h2>{job.title}</h2>
          <span className={`pill ${status.tone}`} title={status.hint}>{status.label}</span>
        </div>
        <p className="job-meta">
          {job.employer ? (
            <span className="job-employer">{job.employer}</span>
          ) : (
            <span className="muted">Employer not named</span>
          )}
          {job.location && (
            <>
              <span className="meta-dot">·</span>
              <span className="job-loc">📍 {job.location}</span>
            </>
          )}
        </p>
        {job.qualification && <p className="job-qual">🎓 {job.qualification}</p>}
        {job.salary_text && <p className="job-salary">💰 {job.salary_text}</p>}
        <p className="job-source">
          <span>{job.newspaper}</span>
          <span className="meta-dot">·</span>
          <span>Printed {fmtDate(job.last_seen_at)}</span>
          {job.appearance_count > 1 && (
            <>
              <span className="meta-dot">·</span>
              <span>{job.appearance_count} editions</span>
            </>
          )}
          {job.has_pending_revision && <span className="pill warn small">Details updated</span>}
        </p>
      </a>
    </li>
  );
}
