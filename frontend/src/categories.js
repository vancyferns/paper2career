// Quick-filter categories, matched by keywords in the job's title and ad text.
export const CATEGORIES = [
  { id: 'hospitality', label: 'Hotels & Food', emoji: '🏨', re: /\b(hotel|resort|restaurant|waiters?|chefs?|cooks?|housekeep\w*|stewards?|bartenders?|kitchen|commis|f&b|front office|caf[eé])\b/i },
  { id: 'driving', label: 'Drivers', emoji: '🚗', re: /\b(drivers?|delivery|chauffeurs?|riders?)\b/i },
  { id: 'office', label: 'Office & Accounts', emoji: '💼', re: /\b(accountants?|accounts|clerks?|office|admin\w*|receptionists?|data entry|computer operators?|back office|tally)\b/i },
  { id: 'sales', label: 'Sales', emoji: '📈', re: /\b(sales\w*|marketing|business development|showroom|counter)\b/i },
  { id: 'teaching', label: 'Teaching', emoji: '📚', re: /\b(teachers?|lecturers?|tutors?|school|college|professors?|faculty)\b/i },
  { id: 'health', label: 'Healthcare', emoji: '🩺', re: /\b(nurses?|nursing|doctors?|pharmac\w*|medical|hospital|clinic|lab tech\w*|physio\w*)\b/i },
  { id: 'technical', label: 'Technical', emoji: '🔧', re: /\b(electricians?|plumbers?|mechanics?|technicians?|engineers?|welders?|fitters?|carpenters?|machinists?|operators?)\b/i },
  { id: 'security', label: 'Security', emoji: '🛡️', re: /\b(security|guards?|watchm[ae]n|bouncers?)\b/i },
];

export function matchesCategory(job, id) {
  const cat = CATEGORIES.find((c) => c.id === id);
  if (!cat) return true;
  return cat.re.test(`${job.title || ''} ${job.description || ''}`);
}
