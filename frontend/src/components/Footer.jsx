import { ShieldIcon, ArrowUpIcon } from './Icons.jsx';

export default function Footer({ hasActionBar = false }) {
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <footer className={`site-footer wrap ${hasActionBar ? 'has-action-bar' : ''}`}>
      <div className="footer-advisory">
        <div className="advisory-badge">
          <ShieldIcon size={16} />
          <span>Safe Job Hunting Advisory</span>
        </div>
        <p>
          Job vacancies are extracted automatically from daily newspaper classifieds. Newspaper publication does not authenticate advertisers. Confirm all terms directly with the employer, and <strong>never pay any fee</strong> to apply, register, or interview.
        </p>
      </div>

      <div className="footer-main">
        <div className="footer-brand">
          <div className="footer-brand-title">
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="" width="28" height="28" className="footer-brand-logo" />
            <span>Paper<span className="grad-text">2</span>Career</span>
          </div>
          <p className="footer-tagline">Newspaper classified jobs in Goa · Updated every morning</p>
        </div>

        <nav className="footer-nav" aria-label="Footer Navigation">
          <a href="#/">All Jobs</a>
          <a href="#/saved">Saved Jobs</a>
          <a href="#/review">Reviewer Queue</a>
          <a href="#/runs">Scraper Runs</a>
          <button type="button" className="btn-back-to-top" onClick={scrollToTop} aria-label="Scroll to top of page">
            <span>Back to top</span>
            <ArrowUpIcon size={14} />
          </button>
        </nav>
      </div>

      <div className="footer-bottom">
        <span>&copy; {new Date().getFullYear()} Paper2Career · Newspaper jobs for a brighter you</span>
        <span className="footer-subtext">Direct 1-tap Call &amp; WhatsApp employer contact</span>
      </div>
    </footer>
  );
}
