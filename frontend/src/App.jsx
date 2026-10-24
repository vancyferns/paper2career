import { useEffect, useRef, useState } from 'react';
import { DEMO } from './api.js';
import { useSaved, visit } from './store.js';
import Feed from './pages/Feed.jsx';
import JobDetail from './pages/JobDetail.jsx';
import Review from './pages/Review.jsx';
import Runs from './pages/Runs.jsx';
import { FlameIcon, HeartIcon, HomeIcon } from './components/Icons.jsx';

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
  const saved = useSaved();
  let view;
  if (page === 'job' && id) view = <JobDetail key={id} id={id} />;
  else if (page === 'review') view = <Review />;
  else if (page === 'runs') view = <Runs />;
  else if (page === 'saved') view = <Feed key="saved" savedOnly />;
  else view = <Feed key="feed" />;

  const tabs = [
    ['#/', 'Jobs', HomeIcon, !page || page === 'job'],
    ['#/saved', 'Saved', HeartIcon, page === 'saved', saved.size],
  ];

  return (
    <>
      <div className="bg-fx" aria-hidden="true">
        <span className="orb orb-a" /><span className="orb orb-b" /><span className="orb orb-c" />
        <span className="grid" />
      </div>

      <header className="topbar">
        <div className="wrap topbar-inner">
          <a href="#/" className="brand">
            <img className="brand-mark" src={`${import.meta.env.BASE_URL}logo.png`} alt="" width="40" height="40" />
            <span className="brand-text">
              <span className="brand-name">Paper<span className="grad-text">2</span>Career</span>
              <span className="brand-tag">Newspaper jobs for a brighter you</span>
            </span>
          </a>
          <nav aria-label="Main" className="top-nav">
            {tabs.map(([href, label, , active, n]) => (
              <a key={href} href={href} aria-current={active ? 'page' : undefined}>
                {label}{n ? <span className="nav-n">{n}</span> : null}
              </a>
            ))}
          </nav>
          {visit.streak > 1 && (
            <span className="streak" title={`You've checked jobs ${visit.streak} days in a row`}>
              <FlameIcon size={14} /> {visit.streak}
            </span>
          )}
          <Menu tabs={tabs} route={page} />
        </div>
      </header>

      {DEMO && (
        <div className="demo-banner" role="note">
          Demo mode: showing data exported by the worker. Set <code>VITE_APPWRITE_*</code> to use the live database.
        </div>
      )}

      <main className={`wrap page ${page === 'job' ? 'has-action-bar' : ''}`}>{view}</main>

      <footer className="wrap footer">
        <p>
          Listings are extracted automatically from newspaper classifieds and updated every morning.
          Newspaper publication does not verify an employer or vacancy. Always confirm details directly with the advertiser,
          and <strong>never pay to apply for a job.</strong>
        </p>
        <div className="footer-links">
          <span>&copy; {new Date().getFullYear()} Paper2Career · Newspaper jobs for a brighter you</span>
          <a href="#/review">Reviewer queue</a>
        </div>
      </footer>

    </>
  );
}

function Menu({ tabs, route }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => { setOpen(false); }, [route]);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('pointerdown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const savedCount = tabs.find(([href]) => href === '#/saved')?.[4];
  return (
    <div className="menu" ref={ref}>
      <button type="button" className={`burger ${open ? 'open' : ''}`} onClick={() => setOpen(!open)}
              aria-expanded={open} aria-controls="main-menu" aria-label={open ? 'Close menu' : 'Open menu'}>
        <span /><span /><span />
        {!open && savedCount ? <span className="burger-dot" aria-hidden="true" /> : null}
      </button>
      {open && (
        <nav id="main-menu" className="menu-panel" aria-label="Main">
          {tabs.map(([href, label, Icon, active, n], i) => (
            <a key={href} href={href} aria-current={active ? 'page' : undefined} style={{ '--i': i }}
               onClick={() => setOpen(false)}>
              <Icon size={18} filled={label === 'Saved' && active} />
              <span>{label}</span>
              {n ? <span className="nav-n">{n}</span> : null}
            </a>
          ))}
        </nav>
      )}
    </div>
  );
}
