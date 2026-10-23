import { useEffect, useState } from 'react';
import { DEMO } from './api.js';
import Feed from './pages/Feed.jsx';
import JobDetail from './pages/JobDetail.jsx';
import Review from './pages/Review.jsx';
import Runs from './pages/Runs.jsx';

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash || '#/');
  useEffect(() => {
    const on = () => {
      setHash(window.location.hash || '#/');
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return hash.slice(1).split('/').filter(Boolean);
}

export default function App() {
  const [page, id] = useHashRoute();
  let view;
  if (page === 'job' && id) view = <JobDetail id={id} />;
  else if (page === 'review') view = <Review />;
  else if (page === 'runs') view = <Runs />;
  else view = <Feed />;

  const nav = (href, label, active) => (
    <a href={href} aria-current={active ? 'page' : undefined}>{label}</a>
  );

  return (
    <>
      <header className="topbar">
        <div className="wrap topbar-inner">
          <a href="#/" className="brand">
            <span className="brand-mark" aria-hidden="true">P2C</span> Paper2Career
          </a>
          <nav aria-label="Main">
            {nav('#/', 'Jobs', !page || page === 'job')}
            {(page === 'runs' || page === 'review') && (
              nav(`#/${page}`, page === 'runs' ? 'Ingestion status' : 'Review queue', true)
            )}
          </nav>
        </div>
      </header>
      {DEMO && (
        <div className="demo-banner" role="note">
          Demo mode: showing data exported by the worker. Set <code>VITE_APPWRITE_*</code> to use the live Appwrite database.
        </div>
      )}
      <main className="wrap">{view}</main>
      <footer className="wrap footer">
        <p style={{ margin: '0 0 1rem' }}>
          Listings are extracted automatically from newspaper classifieds and updated daily.
          Newspaper publication does not verify an employer or vacancy. Always confirm details directly with the advertiser,
          and never pay to apply for a job.
        </p>
        <div style={{ display: 'flex', gap: '1rem', borderTop: '1px solid var(--line)', paddingTop: '0.8rem', fontSize: '0.78rem', color: 'var(--muted)' }}>
          <span>&copy; {new Date().getFullYear()} Paper2Career</span>
          <span aria-hidden="true">•</span>
          <a href="#/runs" style={{ color: 'var(--muted)', textDecoration: 'none' }}>System Status</a>
          <span aria-hidden="true">•</span>
          <a href="#/review" style={{ color: 'var(--muted)', textDecoration: 'none' }}>Reviewer Queue</a>
        </div>
      </footer>
    </>
  );
}
