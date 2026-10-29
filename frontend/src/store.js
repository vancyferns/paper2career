// Per-device conveniences kept in localStorage: saved jobs and visit history (for "new since last visit"
// and the daily streak). Every access is guarded because storage can be blocked (private mode, etc.).
import { useSyncExternalStore } from 'react';
import { daysBetween, today } from './format.js';

function read(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

// ------------------------------------------------------------------ saved jobs

const SAVED_KEY = 'p2c:saved';
let saved = new Set(read(SAVED_KEY, []));
const listeners = new Set();

export function toggleSaved(id) {
  const next = new Set(saved);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  saved = next;
  write(SAVED_KEY, [...next]);
  listeners.forEach((l) => l());
}

export function useSaved() {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => saved,
  );
}

// ------------------------------------------------------------------ visits

const VISIT_KEY = 'p2c:visit';

/** Records today's visit once per day. `prev` is the last day the user came before today. */
function recordVisit() {
  const t = today();
  const v = read(VISIT_KEY, {});
  if (v.last !== t) {
    v.streak = v.last && daysBetween(v.last, t) === 1 ? (v.streak || 1) + 1 : 1;
    v.prev = v.last || null;
    v.last = t;
    write(VISIT_KEY, v);
  }
  return { prev: v.prev || null, streak: v.streak || 1 };
}

export const visit = recordVisit();

// ------------------------------------------------------------------ sharing

/** Native share sheet where available, otherwise copies the link. Returns 'shared' | 'copied' | null. */
export async function shareJob(job) {
  const url = `${window.location.origin}${window.location.pathname}#/job/${job.$id}`;
  const text = `${job.title}${job.employer ? ` at ${job.employer}` : ''}, seen in ${job.newspaper}`;
  if (navigator.share) {
    try {
      await navigator.share({ title: job.title, text, url });
      return 'shared';
    } catch {
      return null;
    }
  }
  try {
    await navigator.clipboard.writeText(`${text}\n${url}`);
    return 'copied';
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ feed search & filter preservation

const FEED_STATE_KEY = 'p2c:feed_state';

const defaultFeedState = {
  q: '',
  location: '',
  deadline: 'any',
  sort: 'recent',
  dateRange: 'today',
  category: '',
  showFilters: false,
  limit: 24,
  scrollY: 0,
};

function readSession(key, fallback) {
  try {
    const v = sessionStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function writeSession(key, val) {
  try {
    sessionStorage.setItem(key, JSON.stringify(val));
  } catch { /* storage unavailable */ }
}

let _feedState = readSession(FEED_STATE_KEY, defaultFeedState);

export function getFeedState() {
  return _feedState;
}

export function saveFeedState(updates) {
  _feedState = { ..._feedState, ...updates };
  writeSession(FEED_STATE_KEY, _feedState);
}

export function resetFeedFilters() {
  _feedState = { ...defaultFeedState, scrollY: 0 };
  writeSession(FEED_STATE_KEY, _feedState);
  return _feedState;
}
