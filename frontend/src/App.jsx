import { useEffect, useRef, useState } from 'react';
import { DEMO } from './api.js';
import { useSaved, visit } from './store.js';
import Feed from './pages/Feed.jsx';
import JobDetail from './pages/JobDetail.jsx';
import Review from './pages/Review.jsx';
import Runs from './pages/Runs.jsx';
import { FlameIcon, HeartIcon, HomeIcon, DownloadIcon } from './components/Icons.jsx';
import { InstallBanner, usePWAInstall, InstallGuideModal } from './components/InstallPrompt.jsx';
import Footer from './components/Footer.jsx';

function useHashRoute() {
  const getRoute = () => {
    // 1. Support Googlebot / canonical query URLs (e.g. ?job=123)
    const params = new URLSearchParams(window.location.search);
    const jobParam = params.get('job');
    if (jobParam) return ['job', jobParam];
    const pageParam = params.get('page');
    if (pageParam) return [pageParam, params.get('id')].filter(Boolean);

    // 2. Default to hash routing (#/job/123)
    const hash = window.location.hash || '#/';
    return hash.slice(1).split('/').filter(Boolean);
  };

  const [route, setRoute] = useState(getRoute);

  useEffect(() => {
    let lastRoute = getRoute();
    const on = () => {
      const nextRoute = getRoute();
      setRoute(nextRoute);
      // Only scroll to top when entering a detail/review/runs page from outside
      // Never force scroll to (0,0) when navigating back to feed
      if (nextRoute[0] && nextRoute[0] !== lastRoute[0]) {
        if (nextRoute[0] === 'job' || nextRoute[0] === 'review' || nextRoute[0] === 'runs') {
          window.scrollTo(0, 0);
        }
      }
      lastRoute = nextRoute;
    };
    window.addEventListener('hashchange', on);
    window.addEventListener('popstate', on);
    return () => {
      window.removeEventListener('hashchange', on);
      window.removeEventListener('popstate', on);
    };
  }, []);

  return route;
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
        <span className="orb orb-a" /><span className="orb orb-b" /><span className="orb orb-c" /><span className="orb orb-d" />
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

      <Footer hasActionBar={page === 'job'} />

      <InstallBanner hide={page === 'job'} />
    </>
  );
}

function Menu({ tabs, route }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const { isInstalled, isIOS, isAndroid, guideOpen, setGuideOpen, triggerInstall } = usePWAInstall();

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
    <>
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
            {!isInstalled && (
              <button
                type="button"
                className="menu-install-btn"
                onClick={() => {
                  setOpen(false);
                  triggerInstall();
                }}
              >
                <DownloadIcon size={18} />
                <span>Install App</span>
              </button>
            )}
          </nav>
        )}
      </div>

      {guideOpen && (
        <InstallGuideModal
          isIOS={isIOS}
          isAndroid={isAndroid}
          onClose={() => setGuideOpen(false)}
        />
      )}
    </>
  );
}
