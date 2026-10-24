import { useEffect, useState } from 'react';
import { DownloadIcon, XIcon, ShareIcon } from './Icons.jsx';

export function usePWAInstall() {
  const [promptEvent, setPromptEvent] = useState(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    // Check if app is already running in standalone/installed mode
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;
    if (standalone) {
      setIsInstalled(true);
      return;
    }

    // Detect iOS
    const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    setIsIOS(ios);

    const onBeforeInstall = (e) => {
      e.preventDefault();
      setPromptEvent(e);
    };

    const onAppInstalled = () => {
      setIsInstalled(true);
      setPromptEvent(null);
    };

    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const install = async () => {
    if (promptEvent) {
      promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      if (choice.outcome === 'accepted') {
        setIsInstalled(true);
      }
      setPromptEvent(null);
      return true;
    }
    return false;
  };

  return { canInstall: Boolean(promptEvent) || (isIOS && !isInstalled), isInstalled, isIOS, install };
}

export function InstallBanner() {
  const { canInstall, isInstalled, isIOS, install } = usePWAInstall();
  const [dismissed, setDismissed] = useState(false);
  const [showIOSModal, setShowIOSModal] = useState(false);

  useEffect(() => {
    const wasDismissed = sessionStorage.getItem('pwa_banner_dismissed');
    if (wasDismissed) setDismissed(true);
  }, []);

  if (isInstalled || !canInstall || dismissed) return null;

  const handleInstallClick = async () => {
    if (isIOS) {
      setShowIOSModal(true);
    } else {
      const ok = await install();
      if (!ok) {
        // Fallback for browsers
        setShowIOSModal(true);
      }
    }
  };

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
            <span>Add to home screen for daily job alerts & 1-tap call</span>
          </div>
        </div>
        <div className="pwa-bar-actions">
          <button type="button" className="btn-install-cta" onClick={handleInstallClick}>
            <DownloadIcon size={15} /> Install App
          </button>
          <button type="button" className="btn-pwa-close" onClick={handleDismiss} aria-label="Dismiss install banner">
            <XIcon size={16} />
          </button>
        </div>
      </aside>

      {showIOSModal && (
        <div className="sheet-backdrop" onClick={() => setShowIOSModal(false)}>
          <div className="sheet pwa-guide-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sheet-head">
              <h2>Install Paper2Career App</h2>
              <button type="button" className="icon-btn" onClick={() => setShowIOSModal(false)}>
                <XIcon size={18} />
              </button>
            </div>
            <div className="sheet-body pwa-guide-body">
              <p>Install this app on your phone for full-screen view and quick daily access:</p>
              <ol className="pwa-steps">
                <li>
                  Tap the <strong>Share</strong> button <ShareIcon size={18} style={{ verticalAlign: '-3px' }} /> at the bottom of your browser.
                </li>
                <li>
                  Scroll down the menu and tap <strong>Add to Home Screen</strong>.
                </li>
                <li>
                  Tap <strong>Add</strong> in the top right corner.
                </li>
              </ol>
            </div>
            <div className="sheet-foot">
              <button type="button" className="btn primary grow" onClick={() => setShowIOSModal(false)}>
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}