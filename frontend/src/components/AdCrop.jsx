import { useState } from 'react';
import { cropUrl } from '../api.js';

/**
 * Shows the advertisement as printed. Prefers the stored crop saved at extraction time (small, and it
 * survives the publisher removing old pages). Falls back to cropping the publisher's page image with CSS.
 */
export default function AdCrop({ appearance, pad = 24, maxHeight = 420 }) {
  const [failed, setFailed] = useState(false);
  const stored = cropUrl(appearance);
  if (stored && !failed) {
    return (
      <div className="adcrop-stored">
        <img src={stored} alt="Scanned newspaper advertisement" loading="lazy" style={{ maxHeight }} onError={() => setFailed(true)} />
      </div>
    );
  }

  const { page_image_url: src, bbox, page_width: pw, page_height: ph } = appearance;
  if (!src || !bbox || bbox.length !== 4 || !pw || !ph) {
    return <p className="muted small">No image of the original ad is stored for this appearance.</p>;
  }
  const x0 = Math.max(0, bbox[0] - pad);
  const y0 = Math.max(0, bbox[1] - pad);
  const w = Math.min(pw, bbox[2] + pad) - x0;
  const h = Math.min(ph, bbox[3] + pad) - y0;
  return (
    <div className="adcrop" style={{ aspectRatio: `${w} / ${h}`, maxWidth: `${(maxHeight * w) / h}px` }}>
      <img
        src={src}
        alt="Scanned newspaper advertisement"
        loading="lazy"
        style={{ width: `${(pw / w) * 100}%`, left: `${(-x0 / w) * 100}%`, top: `${(-y0 / h) * 100}%` }}
      />
    </div>
  );
}
