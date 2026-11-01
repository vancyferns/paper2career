from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

from dateutil.parser import parse as parse_date

from paper2career import extract
from paper2career.models import Advertisement, OcrLine
from paper2career.repository import open_repository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("resync_day")


def resync_jobs_for_date(target_date_str: str, dry_run: bool = False) -> dict:
    repo = open_repository()
    target_date = parse_date(target_date_str).date() if isinstance(target_date_str, str) else target_date_str
    iso_date = target_date.isoformat()

    log.info("Scanning appearances for %s...", iso_date)
    appearances = repo.find("job_appearances", "publication_date", iso_date, limit=2000)
    log.info("Found %d appearances for %s", len(appearances), iso_date)

    if not appearances:
        log.info("Nothing to resync.")
        return {"target_date": iso_date, "appearances_checked": 0, "unique_jobs_checked": 0, "jobs_fixed": 0}

    # ── Batch-load all relevant jobs in ONE query (find_since covers the date window) ──
    # Build a lookup dict: job_id -> job row
    job_ids_needed = {a["job_id"] for a in appearances if a.get("job_id")}
    log.info("Batch-loading %d unique jobs...", len(job_ids_needed))
    # Load all jobs seen on/after (today-2) to cover yesterday and today
    all_jobs_rows = repo.find_since("jobs", "last_seen_at", iso_date, limit=2000)
    # Also grab jobs first seen on this date (new ones) - already covered by find_since with same date
    jobs_map = {j["$id"]: j for j in all_jobs_rows if j["$id"] in job_ids_needed}

    # For any job_ids not found via find_since (e.g. repeat appearances from older editions),
    # fall back individually only for the missing ones
    missing_ids = job_ids_needed - set(jobs_map)
    if missing_ids:
        log.info("Fetching %d missed jobs individually...", len(missing_ids))
        for jid in missing_ids:
            j = repo.get("jobs", jid)
            if j:
                jobs_map[jid] = j

    updated_count = 0
    scanned_jobs = set()

    for app in appearances:
        job_id = app.get("job_id")
        if not job_id:
            continue

        job = jobs_map.get(job_id)
        if not job:
            continue

        scanned_jobs.add(job_id)
        text = app.get("extracted_text") or ""
        if not text:
            continue

        fake_line = OcrLine(text, 0, 0, 100, 20)
        ad = Advertisement(
            text=text,
            lines=[fake_line],
            section=app.get("section"),
            column=0,
            bbox=tuple(app.get("bbox") or [0, 0, 100, 100]),
            ocr_confidence=app.get("confidence") or 0.8,
            ad_reference=app.get("ad_reference"),
        )
        drafts = extract.extract_jobs(ad, target_date)
        if not drafts:
            continue

        role_idx = app.get("role_index", 0)
        draft = next((d for d in drafts if d.role_index == role_idx), drafts[0])

        updates = {}
        for field in ("title", "description", "employer", "location",
                       "qualification", "experience", "salary_text",
                       "application_instructions", "deadline"):
            draft_val = getattr(draft, field, None)
            if job.get(field) != draft_val:
                updates[field] = (draft_val[:255] if field == "title" else
                                   draft_val[:10000] if field == "description" else
                                   draft_val)

        for field in ("contact_phones", "contact_emails"):
            draft_val = getattr(draft, field, [])
            if job.get(field) != draft_val:
                updates[field] = draft_val

        search_tokens = " ".join(filter(None, [
            draft.title,
            draft.location or "",
            extract.normalize_text(draft.description),
            extract.normalize_text(draft.employer or ""),
            " ".join(draft.contact_phones),
        ]))
        updates["search_text"] = search_tokens[:5000]

        if updates:
            log.info("Fixing Job %s (%s): %s", job_id, job.get("title"), list(updates.keys()))
            if not dry_run:
                repo.update("jobs", job_id, updates)
                jobs_map[job_id] = {**job, **updates}  # keep local cache fresh
            updated_count += 1

    summary = {
        "target_date": iso_date,
        "appearances_checked": len(appearances),
        "unique_jobs_checked": len(scanned_jobs),
        "jobs_fixed": updated_count,
    }
    log.info("Resync finished: %s", summary)
    return summary


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-11-01"
    resync_jobs_for_date(date_arg)
