"""Turn OCR lines from a classifieds page into advertisements, then into structured job drafts.

Pipeline:  lines -> columns -> section-tagged blocks -> advertisements -> recruitment filter -> JobDrafts

Everything here is deterministic and engine-agnostic so it can be unit tested with synthetic lines.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, datetime

from dateutil import parser as dateparser
from rapidfuzz import fuzz

from .models import Advertisement, JobDraft, OcrLine

# ---------------------------------------------------------------- section headings

JOB_SECTIONS = (
    "SITUATIONS VACANT", "SITUATION VACANT", "SITUATIONS WANTED", "WANTED", "JOBS", "JOB VACANCY",
    "VACANCIES", "VACANCY", "RECRUITMENT", "APPOINTMENTS", "CAREERS", "STAFF WANTED", "HELP WANTED",
    "EMPLOYMENT",
)
OTHER_SECTIONS = (
    # O Heraldo classifieds headings (several contain "WANTED" but are not jobs)
    "ACC AVAILABLE", "ACC WANTED", "PROPERTIES AVAILABLE", "PROPERTIES WANTED", "PROPERTY AVAILABLE",
    "PROPERTY WANTED", "PREMISES AVAILABLE", "PREMISES WANTED", "VEHICLES AVAILABLE", "VEHICLES WANTED",
    "MISC AVAILABLE", "MISC WANTED", "BUSINESS OFFERS", "PEST CONTROL", "TOURS TRAVELS", "TOURS AND TRAVELS",
    "SHIPPING", "MEDICAL", "MATRIMONIALS", "ENTERTAINMENT", "CONSULTANCY", "CONSULTANCIES",
    # generic
    "PROPERTY", "PROPERTIES", "REAL ESTATE", "FOR SALE", "TO LET", "TO-LET", "RENT", "ACCOMMODATION",
    "VEHICLES", "VEHICLE", "CARS", "AUTOMOBILES", "MATRIMONIAL", "MATRIMONY", "BRIDES", "GROOMS",
    "CHANGE OF NAME", "NAME CHANGE", "PUBLIC NOTICE", "NOTICE", "OBITUARY", "IN MEMORIAM",
    "EDUCATION", "TUITIONS", "ASTROLOGY", "FINANCE", "LOANS", "LOST", "FOUND", "TENDER", "TENDERS",
)
# Mixed sections: jobs are often printed here too, so ads are judged on their own content.
NEUTRAL_SECTIONS = ("GENERAL", "SERVICES", "BUSINESS", "PERSONAL", "MISCELLANEOUS", "CLASSIFIEDS", "CLASSIFIED")
_HEADING_WORDS = {h for h in JOB_SECTIONS + OTHER_SECTIONS + NEUTRAL_SECTIONS}

# ---------------------------------------------------------------- vocabulary

JOB_KEYWORDS = re.compile(
    r"\b(wanted|vacanc(?:y|ies)|required|requirement|recruit\w*|hiring|urgently|openings?|positions?|"
    r"candidates?|applicants?|apply|experience[d]?|qualification|fresher?s?|salary|stipend|walk[- ]?in|"
    r"interview|resume|cv|bio-?data|staff|post of|job|employment)\b",
    re.I,
)
NON_JOB_KEYWORDS = re.compile(
    r"\b(bhk|flat|flats|plot|plots|sq\.?\s?(?:ft|mts?)|bungalow|villa|for sale|on rent|to let|tenant|"
    r"brokerage|registered sale deed|car|cars|bike|scooter|vehicle|kms? driven|model|bride|groom|"
    r"matrimon\w*|alliance|astrolog\w*|loan|loans|tuition|classes|admission|change of name|"
    r"hereby|affidavit|obituary|tender)\b",
    re.I,
)

ROLE_WORDS = (
    "accountant", "accounts assistant", "accounts executive", "account assistant", "receptionist",
    "front office", "driver", "heavy vehicle driver", "cook", "chef", "commis", "helper", "kitchen helper",
    "steward", "waiter", "waitress", "housekeeping", "housekeeper", "room attendant", "security guard", "security",
    "watchman", "nurse", "staff nurse", "ward boy", "ayah", "pharmacist", "lab technician", "teacher",
    "lecturer", "professor", "principal", "electrician", "plumber", "welder", "fitter", "mechanic",
    "technician", "engineer", "site engineer", "civil engineer", "supervisor", "site supervisor",
    "manager", "restaurant manager", "hotel manager", "bar manager", "general manager", "operations manager",
    "kitchen supervisor", "restaurant supervisor", "housekeeping supervisor", "linen supervisor", "shift supervisor",
    "sales executive", "sales manager", "salesman", "salesgirl", "sales person", "sales staff", "salesboy", "sales boy",
    "marketing executive", "field executive", "office assistant", "office boy", "peon", "clerk",
    "data entry operator", "computer operator", "telecaller", "tele caller", "cashier", "storekeeper",
    "store keeper", "delivery boy", "carpenter", "mason", "painter", "tailor", "beautician", "hair stylist",
    "maid", "caretaker", "nanny", "gardener", "mali", "admin executive", "hr executive", "executive",
    "assistant", "operator", "trainee", "intern", "draughtsman", "architect", "pharmacy assistant",
    "doctor", "physiotherapist", "bartender", "barman", "barista", "captain", "bell boy", "lifeguard",
    "packer", "loader", "warehouse", "dishwasher", "cleaner", "store incharge", "factory worker",
    "worker", "labourer", "housekeeping executive", "linen supervisor", "counter boy", "office executive",
    "accounts staff", "service staff", "service boy", "room boy", "housekeeping staff", "cleaning staff",
    "indian chef", "continental chef", "tandoori chef", "tandoor chef", "chinese chef", "goan chef",
    "head chef", "sous chef", "executive chef", "pastry chef", "bakery chef", "pizza chef", "commis chef",
    "indian cook", "continental cook", "tandoori cook", "tandoor cook", "chinese cook", "south indian cook",
    "all rounder cook", "all rounder", "assistant cook", "curry cook", "shawarma cook", "snack cook", "fast food cook",
    "special educator", "educator", "special education teacher", "laboratory assistant", "lab assistant",
    "undergraduate teacher", "primary teacher", "high school teacher", "pre-primary teacher",
    "assistant teacher", "librarian", "library assistant", "counselor", "counsellor", "instructor", "tutor",
)

_ADDRESSEE_ROLES = {
    "manager", "principal", "director", "secretary", "headmaster", "headmistress",
    "incharge", "supervisor", "officer", "administrator", "chairman", "president",
}
_ROLE_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(r) for r in ROLE_WORDS), key=len, reverse=True)) + r")s?\b", re.I
)

GOA_PLACES = (
    "Colva Beach", "Baga Beach", "Calangute Beach", "Candolim Beach", "Miramar Beach", "Benaulim Beach",
    "Mandrem Beach", "Morjim Beach", "Palolem Beach", "Anjuna Beach", "Arambol Beach", "Vagator Beach", "Ashwem Beach",
    "Verna Industrial Estate", "Kundaim Industrial Estate", "Pilerne Industrial Estate", "Tuem Industrial Estate",
    "Tivim Industrial Estate", "Corlim Industrial Estate", "Madkaim Industrial Estate", "Bethora Industrial Estate",
    "Alto Porvorim", "Alto St. Cruz", "Alto Santa Cruz", "Alto Betim", "Dona Paula", "Caranzalem", "Miramar",
    "Santa Cruz", "St. Cruz", "St Cruz", "St. Inez", "St Inez", "Campal", "Ribandar", "Taleigao", "Merces",
    "Panaji", "Panjim", "Margao", "Madgaon", "Vasco", "Vasco da Gama", "Mapusa", "Ponda", "Porvorim",
    "Verna", "Calangute", "Candolim", "Baga", "Anjuna", "Colva", "Benaulim", "Old Goa", "Bicholim",
    "Sanquelim", "Valpoi", "Pernem", "Quepem", "Curchorem", "Canacona", "Sanguem", "Cuncolim",
    "Saligao", "Siolim", "Arpora", "Nagoa", "Kundaim", "Corlim", "Tivim", "Thivim", "Pilerne",
    "Bambolim", "Dabolim", "Cortalim", "Navelim", "Fatorda", "Nuvem", "Majorda", "Varca", "Cavelossim",
    "Mormugao", "Sancoale", "Usgao", "Tisk", "Karaswada", "Bardez", "Salcete", "Tiswadi", "North Goa", "South Goa",
    "Belgaum", "Karwar", "Siridao", "Utorda", "Seraulim", "Colvale", "Assagao", "Raia", "Loutolim",
    "Aquem", "Comba", "Borda", "Gogol", "Davorlim", "Curtorim", "Macasana", "Betalbatim", "Arossim",
    "Cansaulim", "Velsao", "Chinchinim", "Assolna", "Velim", "Betul", "Carmona", "Morjim", "Arambol",
    "Mandrem", "Ashwem", "Vagator", "Chapora", "Oxel", "Camurlim", "Socorro", "Salvador do Mundo",
    "Penha de Franca", "Sangolda", "Guirim", "Parra", "Canca", "Nerul", "Sinquerim", "Reis Magos",
    "Betim", "Britona", "Chorao", "Divar", "Cumbarjua", "Banastarim", "Marcel", "Priol", "Mardol",
    "Farmagudi", "Bandora", "Durbhat", "Borim", "Shiroda", "Panchwadi", "Sanvordem", "Chaudi", "Agonda",
    "Chicalim", "Bogmalo", "Mayem", "Honda", "Pissurlem", "Khandepar", "Goa",
)
_PLACE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, GOA_PLACES), key=len, reverse=True)) + r")\b", re.I)

QUALIFICATION_RE = re.compile(
    r"\b(ssc|hssc|s\.s\.c\.?|h\.s\.s\.c\.?|10th|12th|graduate|graduation|post[- ]?graduate|degree|diploma|"
    r"iti|b\.?\s?com|m\.?\s?com|b\.?\s?sc|m\.?\s?sc|b\.?\s?tech|m\.?\s?tech|"
    r"mba|bba|bca|mca|b\.?\s?ed|d\.?\s?ed|b\.?\s?pharm|d\.?\s?pharm|gnm|anm|b\.?\s?sc\.? nursing|ca inter|"
    r"chartered accountant|tally|ms[- ]?office|computer knowledge|licen[cs]e)\b",
    re.I,
)
# B.A., M.A. and B.E. collide with "ba", "ma" and "be", so they only count when printed in capitals.
QUALIFICATION_CAPS_RE = re.compile(r"\b(B\.\s?A\.?|M\.\s?A\.?|B\.\s?E\.?|BA|MA|BE)(?=[\s,/.)]|$)")
EXPERIENCE_RE = re.compile(
    r"(\b\d+\s*(?:\+|-|to)?\s*\d*\s*(?:yrs?|years?)\.?\s*(?:of\s+)?(?:exp\w*|experience)?|"
    r"\bexperienced\b|\bfreshers?\b(?:\s+(?:can|may)\s+apply)?|\bminimum\s+\d+\s*(?:yrs?|years?))",
    re.I,
)
SALARY_RE = re.compile(
    r"("
    r"\b(?:salary|stipend|pay|ctc)(?:\s+(?:is|starting|minimum|fixed))?\s*[:\-]?"
    r"\s*(?:\brs\.?|inr|₹)?\s*(?![6-9]\d{9}\b)[\d,Oo]{2,7}(?:\s*(?:-|to)\s*(?:\brs\.?|inr|₹)?\s*[\d,Oo]{2,7})?(?:\s*/-|\s*/)?(?:\s*(?:p\.?m\.?|per month|lpa|k\b))?|"
    r"\b(?:(?:minimum|starting|fixed|basic|attractive)\s+)?(?:\brs\.?|inr|₹)?\s*(?![6-9]\d{9}\b)[\d,Oo]{2,7}(?:\s*(?:-|to)\s*(?:\brs\.?|inr|₹)?\s*[\d,Oo]{2,7})?(?:\s*/-|\s*/)?(?:\s*(?:p\.?m\.?|per month|lpa|k\b))?\s*(?:as\s+)?salary\b|"
    r"\b(?:rs\.?|inr|₹)\s*(?![6-9]\d{9}\b)[\d,Oo]{2,7}(?:\s*(?:-|to)\s*(?:\brs\.?|inr|₹)?\s*[\d,Oo]{2,7})?(?:\s*/-|\s*/)?(?:\s*(?:p\.?m\.?|per month|lpa|k\b))?|"
    r"\b(?:minimum|starting|fixed)\s+(?:\brs\.?|inr|₹)?\s*(?![6-9]\d{9}\b)[\d,Oo]{2,7}\s*(?:/-|/|p\.?m\.?|per month)\b|"
    r"\b(?:attractive|negotiable|best in (?:the )?industry|lucrative|handsome)\s+salary\b|"
    r"\bsalary\s+(?:negotiable|no bar|best in (?:the )?industry|as per (?:experience|norms))\b"
    r")",
    re.I,
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?(?:0?832[\s-]?\d{7}|[6-9]\d{4}[\s-]?\d{5})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+\s?@\s?[\w-]+(?:\.[\w-]+)+")
EMPLOYER_RE = re.compile(
    r"([A-Z][\w&.'-]*(?:\s+[A-Z&][\w&.'-]*){0,6}\s+"
    r"(?:Pvt\.?\s*Ltd\.?|Private Limited|Ltd\.?|Limited|LLP|Industries|Enterprises|Hospital|Clinic|"
    r"School|College|Academy|Institute|Hotel|Resort|Restaurant|Bank|Society|Builders|Developers|"
    r"Constructions?|Motors|Pharma|Pharmaceuticals|Group|Associates|Agencies|Traders|Corporation|Co\.))",
)
DEADLINE_RE = re.compile(
    r"(?:last date|apply (?:on or )?before|before|on or before|by|till|latest by|closing date|interview on|"
    r"walk[- ]?in (?:interview )?on)\s*[:\-]?\s*"
    r"(\d{1,2}(?:st|nd|rd|th)?[\s./-]*(?:\d{1,2}|jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|"
    r"sep\w*|oct\w*|nov\w*|dec\w*)[\s.,/-]*(?:\d{2,4})?)",
    re.I,
)
AD_REF_RE = re.compile(r"\b(?:CL|CLS|AD|REF|NO)[\s.:/-]*(\d{4,})\b", re.I)
# O Heraldo prints a 10-digit booking reference (e.g. 2026207841) at the end of every classified ad.
# News stories open with an uppercase place dateline: "MARGAO:", "PANJIM:", "VASCO DA GAMA:".
NEWS_DATELINE_RE = re.compile(r"^[A-Z]{3,}(?:\s[A-Z]{2,}){0,2}:\s")
# Some carry a suffix for a split booking: "2026030842-1".
# Some carry a suffix for a split booking: "2026030842-1". Match anywhere in line as a boundary marker.
AD_TERMINATOR_RE = re.compile(r"(?:^|\D)(20\d{8})(?:\s*-\s*\d{1,2})?(?:\D|$)", re.I)
AD_OPENER_RE = re.compile(
    r"^\s*(wanted|required|urgently\s+required|vacancy|hiring|walk[- ]?in|we\s+are\s+hiring|staff\s+required|"
    r"immediate\s+joining|openings?|looking\s+for|cook\s*&|cook\s+required|driver\s+required|accountant\s+required)\b",
    re.I,
)


PAGE_FURNITURE_RE = re.compile(
    r"^(classifieds?|o\s?heraldo|\d{1,2}|goa,?\s+\w+day,?\s+\w+\s+\d{1,2},?\s+\d{4})$", re.I
)

# ---------------------------------------------------------------- layout

def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", text.upper())).strip()


def match_heading(line: OcrLine, body_height: float) -> str | None:
    """A heading is a short, mostly-uppercase line that names a known section."""
    norm = normalize_heading(line.text)
    if not norm or len(norm.split()) > 4:
        return None
    letters = [c for c in line.text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return None
    for heading in sorted(_HEADING_WORDS, key=len, reverse=True):
        if norm == heading or (norm.startswith(heading) and line.height > body_height * 1.25):
            return heading
    # Reverse-printed headings (white on black) are often misread: "SITUATIONS VAUNT", "MISC AVAUBLE".
    # Accept a close match, but only for lines set larger than body text.
    if line.height >= body_height * 1.1 and len(norm) >= 6:
        best = max(_HEADING_WORDS, key=lambda h: fuzz.ratio(norm, h))
        if fuzz.ratio(norm, best) >= 80:
            return best
    return None


def split_columns(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Find reading columns from the vertical gutters (x ranges almost no text crosses), then assign each
    line to the column holding its centre. Robust to right-aligned and centred lines, unlike left-edge clustering.
    """
    if not lines:
        return []
    # Exclude wide multi-column banners when computing column gutters
    median_w = statistics.median(l.x1 - l.x0 for l in lines)
    col_lines = [l for l in lines if (l.x1 - l.x0) <= median_w * 1.6]
    if not col_lines:
        col_lines = lines

    width = int(max(l.x1 for l in lines)) + 1
    bin_w = max(2, width // 1000)
    coverage = [0] * (width // bin_w + 1)
    for l in col_lines:
        for b in range(int(l.x0) // bin_w, int(l.x1) // bin_w + 1):
            coverage[b] += 1
    # Headlines spanning two columns still cross a gutter, so a gutter is "much emptier", not empty.
    threshold = max(coverage) * 0.10
    min_col = statistics.median(l.x1 - l.x0 for l in lines) * 0.4

    ranges, start = [], None
    for b, c in enumerate(coverage + [0]):
        if c > threshold and start is None:
            start = b
        elif c <= threshold and start is not None:
            ranges.append([start * bin_w, b * bin_w])
            start = None
    # Merge slivers (stray marks) into their nearest neighbour.
    merged: list[list[float]] = []
    for r in ranges:
        if merged and (r[1] - r[0] < min_col or merged[-1][1] - merged[-1][0] < min_col):
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    columns: list[list[OcrLine]] = [[] for _ in merged]
    for l in lines:
        idx = next((i for i, (a, b) in enumerate(merged) if a <= l.cx < b), None)
        if idx is None:
            idx = min(range(len(merged)), key=lambda i: abs((merged[i][0] + merged[i][1]) / 2 - l.cx))
        columns[idx].append(l)
    return [_merge_fragments(c) for c in columns if c]


def _merge_fragments(column: list[OcrLine]) -> list[OcrLine]:
    """Some OCR engines split one justified line into several pieces; rejoin pieces on the same baseline."""
    out: list[OcrLine] = []
    for l in sorted(column, key=lambda l: (l.y0, l.x0)):
        prev = out[-1] if out else None
        # Must be on same baseline AND close horizontally (not across a gutter)
        if (
            prev
            and abs((l.y0 + l.y1) / 2 - (prev.y0 + prev.y1) / 2) < min(l.height, prev.height) * 0.5
            and (l.x0 - prev.x1) <= max(35.0, min(l.height, prev.height) * 2.0)
            and (l.x0 - prev.x1) >= -10.0
        ):
            first, second = (prev, l) if prev.x0 <= l.x0 else (l, prev)
            out[-1] = OcrLine(f"{first.text} {second.text}", min(l.x0, prev.x0), min(l.y0, prev.y0),
                              max(l.x1, prev.x1), max(l.y1, prev.y1), min(l.conf, prev.conf))
        else:
            out.append(l)
    return out


def segment_ads(lines: list[OcrLine]) -> list[Advertisement]:
    """Split a page into advertisements, tagged with the section heading they fall under.

    Columns are read left to right; a heading stays in force until the next heading, even across columns,
    which matches how newspaper classifieds flow.

    Two boundary modes:
      * reference mode - the page prints a booking number at the end of every ad (O Heraldo). Ads end at that
        number and may continue from the bottom of one column to the top of the next.
      * gap mode       - otherwise, a blank gap or a line opening with "Wanted"/"Required"/... starts a new ad.
    """
    lines = [l for l in lines if not PAGE_FURNITURE_RE.match(l.text.strip())]
    if not lines:
        return []
    body_height = statistics.median(l.height for l in lines)
    ref_mode = sum(1 for l in lines if AD_TERMINATOR_RE.match(l.text)) >= 3
    ads: list[Advertisement] = []
    section: str | None = None
    current: list[OcrLine] = []
    current_section: str | None = None

    def flush(ref: str | None = None, term_line: OcrLine | None = None):
        nonlocal current
        if current:
            ads.append(_make_ad(current, current_section, ref, ref_mode, term_line))
            current = []

    for column in split_columns(lines):
        prev: OcrLine | None = None
        if not ref_mode:
            flush()
            # News pages: a boxed heading ("APPOINTMENTS") covers its own column only, unlike classifieds.
            section = None
        for ln in column:
            heading = match_heading(ln, body_height)
            if heading == "WANTED" and ref_mode:
                heading = None      # in numbered layouts a bare "WANTED" is a display ad's banner, not a section
            if heading:
                flush()
                section = heading
                prev = None
                continue

            pure_term = bool(re.match(r"^\W*20\d{8}(?:\s*-\s*\d{1,2})?\W*$", ln.text))
            term = AD_TERMINATOR_RE.search(ln.text)

            if pure_term and ref_mode:
                flush(term.group(1) if term else None, term_line=ln)
                prev = ln
                continue

            gap = ln.y0 - prev.y1 if prev else 0

            # Ad opener: A line clearly starting a new recruitment ad starts a new ad if we already have content
            opener = AD_OPENER_RE.match(ln.text)
            if opener and len(current) >= 2:
                flush()

            gap_break = prev is not None and (gap > body_height * 1.8 if ref_mode else gap > body_height * 0.9)
            if gap_break:
                flush()

            if not current:
                current_section = section
            current.append(ln)
            prev = ln

            # If this line ended with an inline ad reference number, flush the completed ad
            if term and len(current) >= 1:
                flush(term.group(1))
                prev = None
    flush()
    valid_ads = []
    for a in ads:
        if len(a.text) < 25:
            continue
        w = a.bbox[2] - a.bbox[0]
        h = a.bbox[3] - a.bbox[1]
        # Reject thin horizontal strip artifacts across columns (e.g. w>550 and h<70)
        if w >= 480 and h < 75:
            continue
        valid_ads.append(a)
    return valid_ads


def _make_ad(lines: list[OcrLine], section: str | None, ref: str | None = None, ref_mode: bool = False, term_line: OcrLine | None = None) -> Advertisement:
    text = _join_lines(lines)
    if ref is None:
        m = AD_REF_RE.search(text)
        ref = m.group(1) if m else None
    # An ad continued across columns has parts in two places; show the larger part as the evidence crop.
    parts: dict[int, list[OcrLine]] = {}
    col, last_x = 0, None
    for l in lines:
        if last_x is not None and l.x0 > last_x + (l.x1 - l.x0) * 0.6:
            col += 1
        parts.setdefault(col, []).append(l)
        last_x = l.x0
    main = max(parts.values(), key=len)
    # Clamp ad bounding box width to prevent spilling across column boundaries
    med_w = statistics.median(l.x1 - l.x0 for l in main)
    min_x = min(l.x0 for l in main)
    max_x = max(l.x1 for l in main)
    if (max_x - min_x) > med_w * 1.5:
        med_cx = statistics.median(l.cx for l in main)
        min_x = max(min_x, med_cx - med_w * 0.75)
        max_x = min(max_x, med_cx + med_w * 0.75)
    if (max_x - min_x) > 600:
        med_cx = statistics.median(l.cx for l in main)
        min_x = max(min_x, med_cx - 275)
        max_x = min(max_x, med_cx + 275)

    return Advertisement(
        text=text,
        lines=list(lines),
        section=section,
        column=max(parts, key=lambda k: len(parts[k])),
        bbox=(min_x, min(l.y0 for l in main), max_x, max(term_line.y1 if term_line else 0, max(l.y1 for l in main))),
        ocr_confidence=round(statistics.fmean(l.conf for l in lines), 3),
        ad_reference=ref,
        terminated=ref is not None or not ref_mode,
    )


def _join_lines(lines: list[OcrLine]) -> str:
    out = ""
    for ln in lines:
        t = ln.text.strip()
        if out.endswith("-") and t[:1].islower():
            out = out[:-1] + t          # re-join a hyphenated word broken across lines
        else:
            out = f"{out} {t}" if out else t
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------- classification

def recruitment_score(ad: Advertisement) -> float:
    """0..1 likelihood that an advertisement is a recruitment notice."""
    pos = len(JOB_KEYWORDS.findall(ad.text)) + len(_ROLE_RE.findall(ad.text))
    neg = len(NON_JOB_KEYWORDS.findall(ad.text))
    score = 0.5 + 0.12 * pos - 0.2 * neg
    if ad.section in JOB_SECTIONS:
        score += 0.3
    elif ad.section in OTHER_SECTIONS:
        score -= 0.45
    return max(0.0, min(1.0, score))


def is_recruitment(ad: Advertisement) -> bool:
    if NEWS_DATELINE_RE.match(ad.text):
        return False        # "MARGAO: Kala Academy has invited ..." is a news story, not an ad
    has_signal = bool(JOB_KEYWORDS.search(ad.text) or _ROLE_RE.search(ad.text))
    if ad.section in JOB_SECTIONS and ad.terminated:
        # Inside a jobs section, accept anything job-like that isn't clearly something else.
        return has_signal and recruitment_score(ad) >= 0.5
    # Outside (or without) a jobs section, require positive evidence, e.g. a "WANTED Driver" ad in GENERAL.
    return recruitment_score(ad) >= 0.75 and bool(_ROLE_RE.search(ad.text))


def page_recruitment_density(ads: list[Advertisement]) -> float:
    """Used to pick the classifieds page(s) out of a whole edition."""
    if not ads:
        return 0.0
    return sum(1 for a in ads if is_recruitment(a)) / max(len(ads), 1)


# ---------------------------------------------------------------- field extraction

def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" ,.;:-")
    return s or None


def _clean_employer(employer: str | None) -> str | None:
    if not employer:
        return None
    cleaned = re.sub(
        r"^(?:The\s+)?(?:Manager|Principal|Director|Secretary|Chairman|President|Headmaster|Headmistress|Incharge|Officer|Administrator)[,:\s]+",
        "",
        employer,
        flags=re.I,
    )
    return _clean(cleaned)


def _roles(text: str) -> list[str]:
    seen: list[str] = []
    matches = list(_ROLE_RE.finditer(text))
    names = []
    for m in matches:
        matched_str = m.group(1).lower()
        if matched_str in _ADDRESSEE_ROLES:
            pre = text[max(0, m.start() - 60):m.start()]
            if re.search(r"(?:\bto|\bcontact|\bmeet|\breport\s+to|\baddressed\s+to)\s*[:\-]?\s*(?:the\s+)?$", pre, re.I):
                continue

        if names and re.fullmatch(r"\s+cum\s+", text[names[-1][1]:m.start()], re.I):
            names[-1] = (f"{names[-1][0]} cum {m.group(1)}", m.end())      # "Receptionist cum Supervisor"
        else:
            names.append((m.group(1), m.end()))
    for name, _ in names:
        role = name.strip().title().replace(" Cum ", " cum ")
        if not any(role.lower() in r.lower() or r.lower() in role.lower() for r in seen):
            seen.append(role)
    return seen


def _deadline(text: str, published: date) -> str | None:
    m = DEADLINE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    try:
        default = datetime(published.year, published.month, 1)
        parsed = dateparser.parse(raw, dayfirst=True, default=default).date()
    except (ValueError, OverflowError):
        return None
    if not re.search(r"\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2}\b", raw):
        # No year printed: assume the next occurrence after publication.
        if parsed < published:
            try:
                parsed = parsed.replace(year=parsed.year + 1)
            except ValueError:
                return None
    if not (published.replace(year=published.year - 1) <= parsed <= published.replace(year=published.year + 1)):
        return None
    return parsed.isoformat()


def _phones(text: str) -> list[str]:
    phones = []
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if digits not in phones:
            phones.append(digits)
    return phones


def extract_jobs(ad: Advertisement, published: date) -> list[JobDraft]:
    """Extract one JobDraft per distinct role mentioned in the ad. Missing fields stay None."""
    text = ad.text
    # Normalize OCR numeral confusions & separate attached words
    norm_text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    norm_text = re.sub(r'(\d+)[\.,]([Oo]{3})\b', r'\1,000', norm_text)
    norm_text = re.sub(r'(/[-–]?)(\w)', r'\1 \2', norm_text)
    norm_text = re.sub(r'(\d+)\s*[/]\s*[-–]', r'\1/-', norm_text)
    norm_text = re.sub(r'(salary|stipend|pay)\s*\n\s*', r'\1 ', norm_text, flags=re.I)

    roles = _roles(norm_text) or _roles(text) or [None]
    employer = _clean_employer(m.group(1)) if (m := EMPLOYER_RE.search(text)) else None
    place = _PLACE_RE.search(norm_text) or _PLACE_RE.search(text)
    quals = list(dict.fromkeys(_clean(q.group(0)) for q in
                               [*QUALIFICATION_RE.finditer(norm_text), *QUALIFICATION_CAPS_RE.finditer(norm_text)]))
    exp = _clean(m.group(0)) if (m := EXPERIENCE_RE.search(norm_text)) else None

    # Salary extraction with number cleanup
    raw_salary = None
    if m := (SALARY_RE.search(norm_text) or SALARY_RE.search(text)):
        s_val = m.group(0).strip()
        s_val = re.sub(r'(\d+)[,\.]([Oo]{3})\b', r'\1,000', s_val)
        s_val = re.sub(r'(?<=\d)[Oo]+(?=\d|/|\b)', lambda mo: '0' * len(mo.group(0)), s_val)
        raw_salary = _clean(s_val)

    # Detect housing & meals perks common in Goa newspaper ads
    perks = []
    if re.search(r'\b(?:with\s+)?food\s+(?:and|&)\s+accommodation\b|\bwith\s+food\s+and\s+stay\b|\bfood\s+and\s+room\b', norm_text, re.I):
        perks.append("Food & Accommodation provided")
    elif re.search(r'\b(?:free\s+)?accommodation\s+provided\b|\broom\s+provided\b', norm_text, re.I):
        perks.append("Accommodation provided")
    elif re.search(r'\b(?:free\s+)?food\s+provided\b|\bmeals?\s+provided\b', norm_text, re.I):
        perks.append("Food provided")

    salary = raw_salary
    if salary and perks:
        if not any(p.lower() in salary.lower() for p in perks):
            salary = f"{salary} ({', '.join(perks)})"
    elif not salary and perks:
        salary = ", ".join(perks)

    phones = _phones(text)
    emails = list(dict.fromkeys(re.sub(r"\s", "", e).lower() for e in EMAIL_RE.findall(text)))
    deadline = _deadline(text, published)
    apply_m = re.search(r"((?:apply|send|email|mail|forward|contact|call|walk[- ]?in|whatsapp)\b.+?)(?:\.\s+[A-Z]|\.?$)", text, re.I)

    drafts = []
    for idx, role in enumerate(roles):
        uncertain = []
        if role is None:
            uncertain.append("title")
        if not phones and not emails:
            uncertain.append("contact")
        if ad.ocr_confidence < 0.85:
            uncertain.append("ocr_text")
        if len(roles) > 1:
            uncertain.append("multi_role_split")

        signals = [role is not None, bool(phones or emails), bool(place), bool(employer), bool(quals or exp)]
        completeness = sum(signals) / len(signals)
        confidence = round(0.45 * ad.ocr_confidence + 0.35 * completeness + 0.2 * recruitment_score(ad), 3)

        drafts.append(JobDraft(
            title=role or _fallback_title(text),
            employer=employer,
            description=text,
            location=place.group(1).title() if place else None,
            qualification=", ".join(q for q in quals if q) or None,
            experience=exp,
            salary_text=salary,
            contact_phones=phones,
            contact_emails=emails,
            application_instructions=_clean(apply_m.group(1)[:255]) if apply_m else None,
            deadline=deadline,
            confidence=confidence,
            uncertain_fields=uncertain,
            role_index=idx,
        ))
    return drafts


def _fallback_title(text: str) -> str:
    m = re.match(
        r"^\s*(?:wanted|required|urgently required|vacancy|applications? (?:are )?invited for (?:the )?(?:posts?|vacanc\w+) of)\s*[:\-]?"
        r"\s*([^.,:;\n]{3,160})",
        text,
        re.I,
    )
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"\s+[-–—]?\s*(?:ph|tel|call|contact|whatsapp|\d{5,}).*$", "", raw, flags=re.I)
        raw = raw.strip(" -–—/,.:;")
        if len(raw) >= 3:
            return raw.title()
    return "Untitled vacancy (needs review)"


# ---------------------------------------------------------------- normalisation for matching

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9@ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
