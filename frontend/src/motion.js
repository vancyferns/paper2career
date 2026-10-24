// Small animation helpers: scroll-reveal via one shared IntersectionObserver, and a count-up number.
import { useEffect, useRef, useState } from 'react';

export const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

let io;
function observer() {
  if (!io) {
    io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      }
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.06 });
  }
  return io;
}

/** Attach to an element with the `reveal` class; it gains `in` when scrolled into view. */
export function useReveal() {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (!('IntersectionObserver' in window) || reducedMotion()) {
      el.classList.add('in');
      return undefined;
    }
    observer().observe(el);
    return () => observer().unobserve(el);
  }, []);
  return ref;
}

export function useCountUp(target, ms = 1100) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (reducedMotion()) { setValue(target); return undefined; }
    let raf;
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms);
      setValue(Math.round(target * (1 - (1 - p) ** 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

/** Cycles through `items`, returning the current one. */
export function useRotating(items, ms = 2400) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reducedMotion()) return undefined;
    const t = setInterval(() => setI((n) => (n + 1) % items.length), ms);
    return () => clearInterval(t);
  }, [items.length, ms]);
  return items[i];
}

/** Pointer-follow spotlight: sets --mx/--my on the element for a CSS radial glow. */
export function spotlight(e) {
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty('--mx', `${e.clientX - r.left}px`);
  el.style.setProperty('--my', `${e.clientY - r.top}px`);
}
