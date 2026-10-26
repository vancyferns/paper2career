from __future__ import annotations

import logging
import sys
from datetime import date, datetime
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

    log.info("Scanning all job appearances for %s...", iso_date)
    appearances = repo.find("job_appearances", "publication_date", iso_date, limit=2000)
    log.info("Found %d appearances for %s", len(appearances), iso_date)

    updated_count = 0
    scanned_jobs = set()

    for app in appearances:
        job_id = app.get("job_id")
        if not job_id:
            continue

        job = repo.get("jobs", job_id)
        if not job:
            continue

        scanned_jobs.add(job_id)
        text = app.get("extracted_text") or ""
        if not text:
            continue

        # Re-extract clean drafts directly from the appearance's actual text
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

        # Detect corrupted or mismatched fields
        updates = {}
        if job.get("description") != draft.description:
            updates["description"] = draft.description[:10000]

        if job.get("contact_phones") != draft.contact_phones:
            updates["contact_phones"] = draft.contact_phones

        if job.get("contact_emails") != draft.contact_emails:
            updates["contact_emails"] = draft.contact_emails

        if job.get("employer") != draft.employer:
            updates["employer"] = draft.employer

        if job.get("location") != draft.location:
            updates["location"] = draft.location

        if job.get("qualification") != draft.qualification:
            updates["qualification"] = draft.qualification

        if job.get("experience") != draft.experience:
            updates["experience"] = draft.experience

        if job.get("salary_text") != draft.salary_text:
            updates["salary_text"] = draft.salary_text

        if job.get("application_instructions") != draft.application_instructions:
            updates["application_instructions"] = draft.application_instructions

        if job.get("deadline") != draft.deadline:
            updates["deadline"] = draft.deadline

        # Always update search_text
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
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-10-26"
    resync_jobs_for_date(date_arg)
