// Smart partial, fuzzy, and synonym-aware search for jobs in Goa

const COMMON_ABBREVIATIONS = {
  drv: 'driver',
  mgr: 'manager',
  acct: 'accountant',
  acc: 'accountant',
  asst: 'assistant',
  mkt: 'marketing',
  mktg: 'marketing',
  eng: 'engineer',
  engg: 'engineer',
  elec: 'electrician',
  elect: 'electrician',
  tech: 'technician',
  tel: 'telecaller',
  tele: 'telecaller',
  rec: 'receptionist',
  recep: 'receptionist',
  doc: 'doctor',
  pharma: 'pharmacist',
  hk: 'housekeeping',
  sec: 'security',
};

const ALL_GOA_PLACES = [
  'panaji', 'panjim', 'margao', 'madgaon', 'vasco', 'vasco da gama', 'mapusa', 'mapsa',
  'porvorim', 'candolim', 'calangute', 'baga', 'anjuna', 'arambol', 'morjim', 'siolim',
  'assagao', 'saligao', 'guirim', 'pilerne', 'nerul', 'sinquerim', 'bambolim', 'dona paula',
  'santa cruz', 'caranzalem', 'taleigao', 'merces', 'chimbel', 'old goa', 'corlim',
  'ponda', 'tiska', 'kundaim', 'madkai', 'curti', 'borim', 'shiroda', 'benaulim',
  'colva', 'betalbatim', 'majorda', 'utorda', 'cansaulim', 'verna', 'chicalim', 'dabolim',
  'sancoale', 'cortalim', 'cavelossim', 'varca', 'navelim', 'fatorda', 'curtorim', 'cuncolim',
  'quepem', 'curchorem', 'sanvordem', 'sanguem', 'canacona', 'chaudi', 'palolem', 'bicholim',
  'sanquelim', 'valpoi', 'pernem', 'mandrem'
];

const ROLE_SYNONYMS = {
  driver: ['drivers', 'driving', 'chauffeur', 'cab', 'pilot'],
  cook: ['cooks', 'cooking', 'chef', 'chefs', 'kitchen'],
  chef: ['cook', 'cooks', 'cooking', 'kitchen'],
  waiter: ['waiters', 'waitress', 'steward', 'stewards', 'service staff', 'captain'],
  steward: ['waiter', 'waiters', 'stewards', 'service staff'],
  accountant: ['accounts', 'account', 'accounting', 'tally', 'auditor', 'acct'],
  accounts: ['accountant', 'account', 'accounting', 'tally', 'acct'],
  receptionist: ['reception', 'front desk', 'front office', 'telecaller'],
  reception: ['receptionist', 'front desk', 'front office'],
  manager: ['mgr', 'management', 'supervisor', 'incharge'],
  assistant: ['asst', 'helper', 'attendant'],
  helper: ['assistant', 'peon', 'boy', 'maid', 'cleaner'],
  cleaner: ['cleaning', 'housekeeping', 'maid', 'sweeper'],
  housekeeping: ['hk', 'cleaner', 'room boy', 'house keeper'],
  electrician: ['electrical', 'electric', 'wireman'],
  plumber: ['plumbing'],
  mechanic: ['technician', 'tech', 'repair'],
  technician: ['tech', 'mechanic'],
  teacher: ['teaching', 'faculty', 'tutor', 'trainer', 'educator', 'lecturer'],
  nurse: ['nursing', 'sister', 'ward boy', 'attendant', 'hospital', 'clinic'],
  pharmacist: ['pharmacy', 'chemist', 'pharma'],
  security: ['guard', 'watchman', 'security officer', 'bouncer'],
  sales: ['marketing', 'mktg', 'promoter', 'salesman', 'telecaller', 'executive'],
  marketing: ['sales', 'mktg', 'promoter', 'executive'],
  clerk: ['office staff', 'computer operator', 'data entry'],
  operator: ['data entry', 'computer operator', 'clerk'],
  tailor: ['tailoring', 'stitching', 'cutter', 'embroidery'],
};

// Normalize text: lowercase, remove punctuation, collapse whitespace
export function normalize(str) {
  return (str || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Compute simple edit distance (Levenshtein) for short strings
function editDistance(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  if (Math.abs(a.length - b.length) > 1) return 2;

  let prev = [];
  for (let i = 0; i <= b.length; i++) prev[i] = i;

  for (let i = 0; i < a.length; i++) {
    const curr = [i + 1];
    for (let j = 0; j < b.length; j++) {
      const cost = a[i] === b[j] ? 0 : 1;
      curr[j + 1] = Math.min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost);
    }
    prev = curr;
  }
  return prev[b.length];
}

const GOA_SYNONYMS = {
  panaji: ['panjim', 'panajim', 'tiswadi'],
  panjim: ['panaji', 'panajim', 'tiswadi'],
  margao: ['madgaon', 'margoa', 'salcete'],
  madgaon: ['margao', 'margoa', 'salcete'],
  vasco: ['vasco da gama', 'mormugao', 'dabolim'],
  mapusa: ['mapuca', 'mapsa', 'bardez'],
  calangute: ['candolim', 'baga', 'sinquerim'],
  candolim: ['calangute', 'sinquerim'],
  porvorim: ['socorro', 'penha de franca'],
};

// Expand token to synonyms, abbreviations, and partial Goa places
function expandToken(token) {
  const variations = new Set([token]);

  // Check abbreviation
  if (COMMON_ABBREVIATIONS[token]) {
    const full = COMMON_ABBREVIATIONS[token];
    variations.add(full);
    if (ROLE_SYNONYMS[full]) {
      ROLE_SYNONYMS[full].forEach((v) => variations.add(v));
    }
  }

  // Goa places direct synonyms
  if (GOA_SYNONYMS[token]) {
    GOA_SYNONYMS[token].forEach((v) => variations.add(v));
  }

  // If token is prefix of a Goa place (e.g. "panj" -> "panjim" & "panaji", "marg" -> "margao" & "madgaon")
  if (token.length >= 3) {
    for (const place of ALL_GOA_PLACES) {
      if (place.startsWith(token)) {
        variations.add(place);
        if (GOA_SYNONYMS[place]) {
          GOA_SYNONYMS[place].forEach((v) => variations.add(v));
        }
      }
    }
  }

  // Job roles
  if (ROLE_SYNONYMS[token]) {
    ROLE_SYNONYMS[token].forEach((v) => variations.add(v));
  }

  // Also check if token is prefix of any known role
  if (token.length >= 3) {
    for (const [role, syns] of Object.entries(ROLE_SYNONYMS)) {
      if (role.startsWith(token)) {
        variations.add(role);
        syns.forEach((s) => variations.add(s));
      }
    }
  }

  // Common plurals / suffixes
  if (token.endsWith('s') && token.length > 3) {
    variations.add(token.slice(0, -1));
  } else if (!token.endsWith('s')) {
    variations.add(`${token}s`);
  }
  if (token.endsWith('ing') && token.length > 5) {
    variations.add(token.slice(0, -3));
  }

  return [...variations];
}

/**
 * Match a single search term against a text target.
 * Returns score (0 if no match).
 */
function scoreField(term, fieldText, weight) {
  if (!fieldText || !term) return 0;

  const text = normalize(fieldText);
  if (!text) return 0;

  // Exact full phrase in field
  if (text.includes(term)) {
    const isWordStart = new RegExp(`(^|\\s)${term}`, 'i').test(text);
    return isWordStart ? weight * 1.2 : weight;
  }

  // Token expansion (synonyms, abbreviations, plurals, Goa places)
  const expanded = expandToken(term);
  for (const exp of expanded) {
    if (text.includes(exp)) {
      const isWordStart = new RegExp(`(^|\\s)${exp}`, 'i').test(text);
      return isWordStart ? weight * 1.1 : weight * 0.95;
    }
  }

  // Partial prefix match on words (e.g. "acc" -> "accountant", "drv" -> "driver", "panj" -> "panaji")
  const words = text.split(/\s+/);
  for (const w of words) {
    if (term.length >= 3) {
      // Substring match inside word (e.g. "teach" inside "teachers")
      if (w.includes(term)) {
        return weight * 0.9;
      }
      // Or word inside term
      if (term.startsWith(w) && w.length >= 4) {
        return weight * 0.8;
      }
      // Check expanded variations against word
      for (const exp of expanded) {
        if (w.includes(exp) || exp.includes(w)) {
          return weight * 0.85;
        }
      }
      // Fuzzy match (1 letter typo, only for 4+ letters)
      if (term.length >= 4 && w.length >= 4 && editDistance(term, w) <= 1) {
        return weight * 0.75;
      }
    }
  }

  return 0;
}


/**
 * Score a job against a user search query.
 * Checks Title (weight 100), Location (weight 60), Description (weight 35), Employer (weight 40).
 * Returns { matches: boolean, score: number }.
 */
export function scoreJob(job, rawQuery) {
  const q = normalize(rawQuery);
  if (!q) return { matches: true, score: 0 };

  const terms = q.split(/\s+/).filter(Boolean);
  if (terms.length === 0) return { matches: true, score: 0 };

  let totalScore = 0;
  let termsMatched = 0;

  const titleText = job.title || '';
  const locText = job.location || '';
  const descText = job.description || '';
  const empText = job.employer || '';
  const qualText = [job.qualification, job.experience].filter(Boolean).join(' ');

  for (const term of terms) {
    let termScore = 0;

    // Check title (highest priority)
    const tScore = scoreField(term, titleText, 100);
    if (tScore > 0) termScore = Math.max(termScore, tScore);

    // Check location
    const lScore = scoreField(term, locText, 60);
    if (lScore > 0) termScore = Math.max(termScore, lScore);

    // Check employer
    const eScore = scoreField(term, empText, 45);
    if (eScore > 0) termScore = Math.max(termScore, eScore);

    // Check description
    const dScore = scoreField(term, descText, 35);
    if (dScore > 0) termScore = Math.max(termScore, dScore);

    // Check qualification & experience
    const qScore = scoreField(term, qualText, 25);
    if (qScore > 0) termScore = Math.max(termScore, qScore);

    if (termScore > 0) {
      termsMatched += 1;
      totalScore += termScore;
    }
  }

  // All query terms must match at least something (or if 3+ terms, at least (n-1) must match)
  const minRequired = terms.length >= 3 ? terms.length - 1 : terms.length;
  const matches = termsMatched >= minRequired;

  if (matches) {
    // Big bonus if ALL terms matched
    if (termsMatched === terms.length) {
      totalScore *= 1.5;
    }
    // Huge bonus if title alone contains multiple matching terms
    const fullInTitle = scoreField(q, titleText, 150);
    if (fullInTitle > 0) totalScore += fullInTitle;
  }

  return {
    matches,
    score: matches ? totalScore : 0,
  };
}
