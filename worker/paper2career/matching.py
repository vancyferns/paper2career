"""Duplicate detection and change tracking across editions.

Signals, strongest first (all require a similar role title):
  1. identical normalised ad text (content hash)                  -> exact repeat, linked automatically
  2. text similarity >= 93 and no conflicting contacts            -> repeat with OCR noise, linked automatically
  3. a shared phone/email, or similarity >= 80 without conflicting
     contacts, or >= 97 even with different contacts               -> probable match, linked but flagged for review
Whenever a linked ad differs in a key field (deadline, salary, contact, ...), a revision is recorded for review.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .extract import normalize_text
from .models import JobDraft

AUTO_TEXT_SCORE = 93
PROBABLE_TEXT_SCORE = 80
TITLE_SCORE = 85
CONFLICT_TEXT_SCORE = 97   # different contacts, but the ad text is otherwise the same: possibly a revised ad

TRACKED_FIELDS = ("deadline", "salary_text", "contact_phones", "contact_emails", "location",
                  "qualification", "experience", "employer")


@dataclass
class MatchResult:
    kind: str                       # "new" | "exact" | "repeat" | "probable"
    job: dict | None = None
    score: float = 0.0
    changes: dict[str, tuple] = field(default_factory=dict)

    @property
    def needs_review(self) -> bool:
        return self.kind == "probable" or bool(self.changes)


def changed_fields(job: dict, draft: JobDraft) -> dict[str, tuple]:
    """Fields that both appearances state, but differently. A field missing from either side is not a change:
    a newly readable value only fills a gap (see `filled_fields`)."""
    changes = {}
    for name in TRACKED_FIELDS:
        new = getattr(draft, name)
        old = job.get(name)
        if new in (None, "", []) or old in (None, "", []):
            continue
        if isinstance(new, list):
            if sorted(new) != sorted(old or []):
                changes[name] = (old or [], new)
        elif normalize_text(str(new)) != normalize_text(str(old or "")):
            changes[name] = (old, new)
    return changes


def filled_fields(job: dict, draft: JobDraft) -> dict:
    """Values the new appearance supplies for fields the canonical job left unknown."""
    return {name: getattr(draft, name) for name in TRACKED_FIELDS
            if job.get(name) in (None, "", []) and getattr(draft, name) not in (None, "", [])}


def find_match(draft: JobDraft, ad_text: str, exact_job: dict | None, candidates: list[dict]) -> MatchResult:
    if exact_job is not None:
        return MatchResult("exact", exact_job, 100.0, changed_fields(exact_job, draft))

    norm = normalize_text(ad_text)
    contacts = set(draft.contact_phones) | set(draft.contact_emails)
    best: MatchResult = MatchResult("new")

    for job in candidates:
        # Plain character similarity, not token_set_ratio: the latter scores 100 whenever one ad's words are a
        # subset of another's, which links unrelated ads (seen on real pages).
        text_score = fuzz.ratio(norm, normalize_text(job.get("description", "")))
        title_score = fuzz.token_sort_ratio(draft.title.lower(), (job.get("title") or "").lower())
        job_contacts = set(job.get("contact_phones") or []) | set(job.get("contact_emails") or [])
        shared_contact = bool(contacts & job_contacts)
        # Both ads print contacts and none overlap: a different advertiser unless the text is near-identical.
        conflicting_contact = bool(contacts and job_contacts and not shared_contact)
        if title_score < TITLE_SCORE:
            continue
        if text_score >= AUTO_TEXT_SCORE and not conflicting_contact:
            kind = "repeat"
        elif shared_contact or (text_score >= PROBABLE_TEXT_SCORE and not conflicting_contact) \
                or text_score >= CONFLICT_TEXT_SCORE:
            kind = "probable"
        else:
            continue
        score = text_score + (5 if shared_contact else 0)
        rank = {"repeat": 2, "probable": 1}
        if rank[kind] > rank.get(best.kind, 0) or (kind == best.kind and score > best.score):
            best = MatchResult(kind, job, float(score))

    if best.job is not None:
        best.changes = changed_fields(best.job, draft)
    return best
