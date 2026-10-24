import { ShieldIcon } from './Icons.jsx';

export default function Footer({ hasActionBar = false }) {
  return (
    <footer className={`site-footer wrap ${hasActionBar ? 'has-action-bar' : ''}`}>
      {!hasActionBar && (
        <div className="footer-advisory">
          <div className="advisory-badge">
            <ShieldIcon size={16} />
            <span>Safe Job Hunting Advisory</span>
          </div>
          <p>
            Job vacancies are extracted automatically from daily newspaper classifieds. Newspaper publication does not authenticate advertisers. Confirm all terms directly with the employer, and <strong>never pay any fee</strong> to apply, register, or interview.
          </p>
        </div>
      )}

      <div className="footer-bottom">
        <div className="footer-brand">
          <div className="footer-brand-title">
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="" width="26" height="26" className="footer-brand-logo" />
            <span>Paper<span className="grad-text">2</span>Career</span>
          </div>
          <span className="footer-tagline">Newspaper classified jobs in Goa · Updated every morning</span>
        </div>

        <div className="footer-meta">
          <span>&copy; {new Date().getFullYear()} Paper2Career · Newspaper jobs for a brighter you</span>
          <span className="footer-subtext">Direct 1-tap Call &amp; WhatsApp employer contact</span>
        </div>
      </div>
    </footer>
  );
}
