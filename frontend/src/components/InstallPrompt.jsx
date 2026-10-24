import { useEffect, useState } from 'react';
import { DownloadIcon, XIcon, ShareIcon } from './Icons.jsx';

// Shared event listener so both banner and menu button have immediate access
let globalPromptEvent = null;
const promptListeners = new Set();

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    globalPromptEvent = e;
    promptListeners.forEach((fn) => fn(e));
  });

  window.addEventListener('appinstalled', () => {
    globalPromptEvent = null;
    promptListeners.forEach((fn) => fn(null));
  });
}

export function usePWAInstall() {
  const [promptEvent, setPromptEvent] = useState(globalPromptEvent);
  const [isInstalled, setIsInstalled] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [isAndroid, setIsAndroid] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  useEffect(() => {
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;
    if (standalone) {
      setIsInstalled(true);
      return;
    }

    const ua = navigator.userAgent || '';
    const ios = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    const android = /Android/i.test(ua);
    setIsIOS(ios);
    setIsAndroid(android);

    const handler = (e) => setPromptEvent(e);
    promptListeners.add(handler);
    return () => promptListeners.delete(handler);
  }, []);

  const triggerInstall = async () => {
    if (promptEvent) {
      promptEvent.prompt();
      try {
        const choice = await promptEvent.userChoice;
        if (choice && choice.outcome === 'accepted') {
          setIsInstalled(true);
        }
      } catch {
        // ignore
      }
      globalPromptEvent = null;
      setPromptEvent(null);
      return true;
    }
    // If native prompt unavailable, show guidance modal
    setGuideOpen(true);
    return false;
  };

  return {
    canInstall: !isInstalled,
    isInstalled,
    isIOS,
    isAndroid,
    hasNativePrompt: Boolean(promptEvent),
    guideOpen,
    setGuideOpen,
    triggerInstall,
  };
}

export function InstallGuideModal({ isIOS, isAndroid, onClose }) {
  return (
    <div className="sheet-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="How to install Paper2Career">
      <div className="sheet pwa-guide-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <h2>Install Paper2Career App</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close guide">
            <XIcon size={18} />
          </button>
        </div>
        <div className="sheet-body pwa-guide-body">
          <p style={{ margin: '0 0 0.75rem', color: 'var(--muted)' }}>
            Install on your phone for instant home-screen access, full-screen viewing, and fast 1-tap call to employers:
          </p>

          {isIOS ? (
            <ol className="pwa-steps">
              <li>
                Make sure you are viewing in <strong>Safari</strong>.
              </li>
              <li>
                Tap the <strong>Share</strong> button <ShareIcon size={17} style={{ verticalAlign: '-3px' }} /> at the bottom of the screen.
              </li>
              <li>
                Scroll down and select <strong>&quot;Add to Home Screen&quot;</strong>.
              </li>
              <li>
                Tap <strong>Add</strong> in the top-right corner.
              </li>
            </ol>
          ) : isAndroid ? (
            <ol className="pwa-steps">
              <li>
                Make sure you are viewing in <strong>Chrome</strong> (not WhatsApp/Instagram preview).
              </li>
              <li>
                Tap the <strong>three dots menu (⋮)</strong> at the top right of Chrome.
              </li>
              <li>
                Tap <strong>&quot;Install app&quot;</strong> or <strong>&quot;Add to Home screen&quot;</strong>.
              </li>
              <li>
                Tap <strong>Install</strong> to confirm.
              </li>
            </ol>
          ) : (
            <ol className="pwa-steps">
              <li>
                In your browser&apos;s address bar, look for the <strong>Install</strong> icon <DownloadIcon size={16} style={{ verticalAlign: '-2px' }} />.
              </li>
              <li>
                Or open your browser menu (⋮) and click <strong>&quot;Install Paper2Career&quot;</strong>.
              </li>
            </ol>
          )}
        </div>
        <div className="sheet-foot">
          <button type="button" className="btn primary grow" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}

export function InstallBanner() {
  const { isInstalled, isIOS, isAndroid, guideOpen, setGuideOpen, triggerInstall } = usePWAInstall();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const wasDismissed = sessionStorage.getItem('pwa_banner_dismissed');
    if (wasDismissed) setDismissed(true);
  }, []);

  if (isInstalled || dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem('pwa_banner_dismissed', '1');
  };

  return (
    <>
      <aside className="pwa-install-bar" aria-label="Install App Banner">
        <div className="pwa-bar-left">
          <img src={`${import.meta.env.BASE_URL}favicon.png`} alt="" className="pwa-bar-icon" width="36" height="36" />
          <div className="pwa-bar-text">
            <strong>Install Paper2Career</strong>
            <span>Add to home screen for daily job alerts</span>
          </div>
        </div>
        <div className="pwa-bar-actions">
          <button type="button" className="btn-install-cta" onClick={() => triggerInstall()}>
            <DownloadIcon size={15} /> Install
          </button>
          <button type="button" className="btn-pwa-close" onClick={handleDismiss} aria-label="Dismiss banner">
            <XIcon size={16} />
          </button>
        </div>
      </aside>

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
