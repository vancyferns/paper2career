// Quick-filter categories, matched strictly against the job's extracted title.
export const CATEGORIES = [
  { id: 'driving', label: 'Drivers & Delivery', emoji: '🚗', re: /\b(drivers?|delivery|chauffeurs?|riders?|transport)\b/i },
  { id: 'office', label: 'Office & Accounts', emoji: '💼', re: /\b(accountants?|accounts?|clerks?|office|admin\w*|receptionists?|data entry|computer operators?|back office|tally|telecall\w*|counselors?|hr\b|cashiers?)\b/i },
  { id: 'hospitality', label: 'Hotels & Food', emoji: '🏨', re: /\b(cooks?|chefs?|waiters?|waitress\w*|stewards?|stewardess\w*|bartenders?|barman|kitchen|commis|housekeep\w*|houseman|room boy|bellboy|f&b|restaurant|hotel|resort|captains?)\b/i },
  { id: 'helpers', label: 'Helpers & Cleaning', emoji: '🧹', re: /\b(helpers?|maids?|cleaners?|sweepers?|peons?|dishwashers?|all rounders?|caretakers?|nanny|babysitters?)\b/i },
  { id: 'sales', label: 'Sales & Marketing', emoji: '📈', re: /\b(sales\w*|marketing|business dev\w*|showroom|counter staff|promoters?|salesman|salesgirl|sales boy)\b/i },
  { id: 'technical', label: 'Technical & Trades', emoji: '🔧', re: /\b(electricians?|plumbers?|mechanics?|technicians?|engineers?|welders?|fitters?|carpenters?|machinists?|operators?|wirem[ae]n|ac tech\w*)\b/i },
  { id: 'health', label: 'Healthcare', emoji: '🩺', re: /\b(nurses?|nursing|doctors?|pharmac\w*|medical|hospital|clinic|lab tech\w*|dentists?|physio\w*)\b/i },
  { id: 'teaching', label: 'Teaching', emoji: '📚', re: /\b(teachers?|lecturers?|tutors?|school|college|professors?|faculty|instructors?)\b/i },
  { id: 'security', label: 'Security', emoji: '🛡️', re: /\b(security\w*|guards?|watchm[ae]n|bouncers?)\b/i },
];

export function matchesCategory(job, id) {
  const cat = CATEGORIES.find((c) => c.id === id);
  if (!cat) return true;
  const title = (job.title || '').trim();

  // 1. Strict match on extracted title (prevents false matches from ad body text)
  if (cat.re.test(title)) return true;

  // 2. Fallback to description only if title was not extracted or is generic
  const isGeneric = !title || /^(untitled|vacancy|requirement|urgent|staff|wanted)\b/i.test(title);
  if (isGeneric && job.description) {
    return cat.re.test(job.description);
  }
  return false;
}
