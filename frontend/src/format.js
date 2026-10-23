export const today = () => new Date().toISOString().slice(0, 10);

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

/**
 * Status shown to job seekers. We never claim a vacancy is open or closed; we report what the ad said
 * and how recently it was printed.
 */
export function listingStatus(job) {
  const t = today();
  if (job.deadline && job.deadline < t) {
    return { tone: 'muted', label: `Deadline passed ${fmtDate(job.deadline)}`, hint: 'The ad’s stated deadline has passed. The post may or may not still be open.' };
  }
  if (job.deadline) {
    const left = daysBetween(t, job.deadline);
    return { tone: left <= 3 ? 'warn' : 'ok', label: left === 0 ? 'Deadline today' : `Apply by ${fmtDate(job.deadline)}`, hint: 'Deadline as printed in the advertisement.' };
  }
  const age = daysBetween(job.last_seen_at, t);
  if (age > 30) {
    return { tone: 'muted', label: `Last advertised ${age} days ago`, hint: 'No deadline was printed. This listing may be stale.' };
  }
  return { tone: 'neutral', label: 'No deadline stated', hint: 'The advertisement did not print a deadline.' };
}

export const UNKNOWN = 'Not stated in ad';
