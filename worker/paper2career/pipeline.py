"""Daily ingestion: discover -> acquire -> OCR -> classify -> extract -> match -> store -> log."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from . import extract, ocr
from .config import settings
from .matching import filled_fields, find_match
from .models import Advertisement, JobDraft, OcrLine
from .repository import Repository
from .source import AcquiredPage, EditionRef, HeraldoSource, LayoutChanged, PageRef, SourceUnavailable

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
CLASSIFIED_MARKERS = re.compile(
    r"\b(classifieds?|situations? vacant|wanted|vacanc(?:y|ies)|recruitment|appointments?|walk[- ]?in)\b", re.I
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(text: str, n: int = 64) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


@dataclass
class RunStats:
    editions_checked: int = 0
    editions_found: int = 0
    editions_processed: int = 0
    pages_processed: int = 0
    pages_failed: int = 0
    ads_found: int = 0
    jobs_extracted: int = 0
    new_jobs: int = 0
    repeat_appearances: int = 0
    revisions_flagged: int = 0
    skipped_existing: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- OCR cache

def page_lines(path: Path, checksum: str) -> list[OcrLine]:
    """OCR a page, caching by file checksum so re-runs and retries don't redo slow OCR."""
    cache = path.with_suffix(f".{checksum[:12]}.ocr.json")
    if cache.exists():
        return [OcrLine(**d) for d in json.loads(cache.read_text(encoding="utf-8"))]
    lines = ocr.ocr_file(path)
    cache.write_text(json.dumps([asdict(l) for l in lines]), encoding="utf-8")
    return lines


def looks_like_classifieds(path: Path) -> bool:
    """Cheap pre-screen on the ~800 px page preview: look for classifieds/recruitment headings.

    Previews are upscaled 2x first; at native size the small headings are below what OCR can read.
    """
    with Image.open(path) as img:
        img = img.convert("RGB")
        if img.width < 1600:
            img = img.resize((img.width * 2, img.height * 2))
    text = " ".join(l.text for l in ocr.ocr_image(img))
    hits = len(CLASSIFIED_MARKERS.findall(text))
    log.info("  %s: %d classifieds markers", path.name, hits)
    return hits >= 2


# ---------------------------------------------------------------- ingestion

class Ingestor:
    def __init__(self, repo: Repository, source: HeraldoSource | None = None, auto_publish: bool | None = None):
        self.repo = repo
        self.source = source or HeraldoSource()
        self.auto_publish = settings.auto_publish if auto_publish is None else auto_publish

    # ---- runs

    def run(self, days: list[date] | None = None, trigger: str = "schedule", pages: list[int] | None = None,
            force: bool = False) -> dict:
        run_id = "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:24]
        stats = RunStats()
        self.repo.create("ingestion_runs", run_id, {
            "started_at": now_iso(), "status": "RUNNING", "trigger": trigger,
        })
        status, error = "FAILED", None
        try:
            today = datetime.now(IST).date()
            # Fetch and process today's edition first
            days = days or [today - timedelta(days=n) for n in range(settings.lookback_days)]
            for day in days:
                stats.editions_checked += 1
                edition_id = f"ed_{settings.source_alias}-{day.isoformat()}"[:36]
                existing = self.repo.get("editions", edition_id)
                if existing and existing.get("status") in ("PROCESSED", "NO_RECRUITMENT_FOUND") and not force:
                    log.info("Edition %s already processed; skipping", edition_id)
                    stats.skipped_existing += 1
                    continue

                edition = self.source.find_edition(day)
                if edition is None:
                    log.info("No %s edition published for %s (yet)", settings.newspaper_name, day)
                    continue
                stats.editions_found += 1
                self.process_edition(edition, stats, only_pages=pages, force=force)

            if stats.editions_processed == 0:
                status = "NO_NEW_EDITION"
            elif stats.pages_failed:
                status = "PARTIAL"
            else:
                status = "SUCCESS"
        except (SourceUnavailable, LayoutChanged) as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.error(error)
        except Exception as exc:  # noqa: BLE001 - every failure must end up in the run log
            error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-3000:]}"
            log.exception("Ingestion crashed")
        finally:
            summary = {k: v for k, v in asdict(stats).items() if k != "notes"}
            self.repo.update("ingestion_runs", run_id, {
                "finished_at": now_iso(), "status": status, "error_message": (error or "")[:5000] or None,
                "notes": "\n".join(stats.notes)[:5000] or None, **summary,
            })
        log.info("Run %s finished: %s %s", run_id, status, summary)

        # Automatically prune crops & records older than RETENTION_DAYS (default: 7) to keep storage minimal
        try:
            import os
            retention_days = int(os.environ.get("RETENTION_DAYS", "7"))
            self.prune_older_than(days=retention_days)
        except Exception as exc:
            log.warning("Auto-prune failed: %s", exc)

        return {"run_id": run_id, "status": status, **summary, "error": error}

    def prune_older_than(self, days: int = 7) -> dict:
        """Delete ad crops and appearances older than `days` to save storage in Appwrite."""
        # Retention window: keep today and preceding (days - 1) days.
        # Any record on or before cutoff date is pruned.
        cutoff = (datetime.now(IST).date() - timedelta(days=days)).isoformat()
        log.info("Pruning records older than %d days (cutoff: <= %s)", days, cutoff)

        pruned_crops = 0
        pruned_appearances = 0
        pruned_jobs = 0
        pruned_editions = 0

        # 1. Prune job appearances and their ad crops from storage
        old_appearances = self.repo.find_before_or_on("job_appearances", "publication_date", cutoff, limit=5000)
        for a in old_appearances:
            crop_id = a.get("crop_file_id")
            if crop_id:
                try:
                    self.repo.delete_crop(crop_id)
                    pruned_crops += 1
                except Exception as exc:
                    log.debug("Crop delete skipped for %s: %s", crop_id, exc)
            self.repo.delete("job_appearances", a["$id"])
            pruned_appearances += 1

        # 2. Prune jobs whose last appearance was before or on cutoff
        old_jobs = self.repo.find_before_or_on("jobs", "last_seen_at", cutoff, limit=5000)
        for j in old_jobs:
            self.repo.delete("jobs", j["$id"])
            pruned_jobs += 1

        # 3. Prune old editions
        for e in self.repo.all("editions", limit=1000):
            ed_date = e.get("publication_date")
            if not ed_date and e.get("$id", "").startswith("ed_"):
                parts = e["$id"].split("-", 1)
                if len(parts) == 2 and len(parts[1]) == 10:
                    ed_date = parts[1]
            if ed_date and ed_date <= cutoff:
                if self.repo.delete("editions", e["$id"]):
                    pruned_editions += 1

        res = {
            "cutoff": cutoff,
            "pruned_crops": pruned_crops,
            "pruned_appearances": pruned_appearances,
            "pruned_jobs": pruned_jobs,
            "pruned_editions": pruned_editions,
        }
        log.info("Pruning complete: %s", res)
        return res

    def process_edition(self, edition: EditionRef, stats: RunStats, only_pages: list[int] | None = None,
                        force: bool = False) -> None:
        edition_id = f"ed_{edition.edition_key}"[:36]
        existing = self.repo.get("editions", edition_id)
        if existing and existing.get("status") in ("PROCESSED", "NO_RECRUITMENT_FOUND") and not force:
            log.info("Edition %s already processed; skipping", edition.edition_key)
            return

        self.repo.upsert("editions", edition_id, {
            "edition_key": edition.edition_key, "newspaper": settings.newspaper_name,
            "publication_date": edition.publication_date.isoformat(), "source_url": edition.source_url,
            "source_edition_id": edition.source_edition_id, "page_count": len(edition.pages),
            "status": "PROCESSING",
        })

        # Screen cheap previews first, then download only the classifieds page(s) at full resolution.
        failed = 0
        wanted: list[PageRef] = []
        for page in edition.pages:
            if only_pages:
                if page.page_number in only_pages:
                    wanted.append(page)
                continue
            try:
                if looks_like_classifieds(self.source.download_preview(page, edition.edition_key)):
                    wanted.append(page)
            except SourceUnavailable as exc:
                failed += 1
                stats.notes.append(f"{edition.edition_key} p{page.page_number} preview: {exc}")

        acquired: list[AcquiredPage] = []
        for page in wanted:
            try:
                acquired.append(self.source.download_page(page, edition.edition_key))
            except SourceUnavailable as exc:
                failed += 1
                stats.notes.append(f"{edition.edition_key} p{page.page_number}: {exc}")
        classified = acquired
        if not classified:
            stats.notes.append(f"{edition.edition_key}: no classifieds page detected")

        jobs_before = stats.jobs_extracted
        for page in classified:
            try:
                self.process_page(edition, page.page, page.path, page.checksum, stats)
            except Exception as exc:  # noqa: BLE001 - one bad page shouldn't sink the edition
                failed += 1
                log.exception("Page %s failed", page.page.page_number)
                stats.notes.append(f"{edition.edition_key} p{page.page.page_number}: {type(exc).__name__}: {exc}")

        stats.pages_failed += failed
        stats.editions_processed += 1
        found = stats.jobs_extracted - jobs_before
        if found and self.auto_publish:
            self.resync_edition_jobs(edition.publication_date)
        status = "PARTIAL" if failed else ("PROCESSED" if found else "NO_RECRUITMENT_FOUND")
        self.repo.update("editions", edition_id, {
            "status": status, "processed_at": now_iso(), "jobs_found": found,
            "classified_pages": [p.page.page_number for p in classified],
            "checksum": sha("".join(sorted(a.checksum for a in acquired))),
        })

    def resync_edition_jobs(self, pub_date: date) -> int:
        """Scan all appearances for pub_date and ensure canonical job metadata strictly matches the clipping."""
        iso_date = pub_date.isoformat()
        appearances = self.repo.find("job_appearances", "publication_date", iso_date, limit=2000)
        fixed = 0
        for app in appearances:
            job_id = app.get("job_id")
            if not job_id:
                continue
            job = self.repo.get("jobs", job_id)
            if not job:
                continue
            text = app.get("extracted_text") or ""
            if not text:
                continue
            fake_line = OcrLine(text, 0, 0, 100, 20)
            ad = Advertisement(
                text=text, lines=[fake_line], section=app.get("section"),
                column=0, bbox=tuple(app.get("bbox") or [0, 0, 100, 100]),
                ocr_confidence=app.get("confidence") or 0.8,
                ad_reference=app.get("ad_reference"),
            )
            drafts = extract.extract_jobs(ad, pub_date)
            if not drafts:
                continue
            role_idx = app.get("role_index", 0)
            draft = next((d for d in drafts if d.role_index == role_idx), drafts[0])

            updates = {}
            for f in ("title", "description", "contact_phones", "contact_emails", "employer",
                      "location", "qualification", "experience", "salary_text",
                      "application_instructions", "deadline"):
                if job.get(f) != getattr(draft, f):
                    updates[f] = getattr(draft, f)
            if updates:
                updates["search_text"] = _search_text(draft)[:5000]
                self.repo.update("jobs", job_id, updates)
                fixed += 1
        if fixed:
            log.info("Auto-resync for %s: verified and fixed %d jobs to match clippings", iso_date, fixed)
        return fixed

    def import_file(self, path: Path, publication_date: date, page_number: int, source_url: str | None = None,
                    image_url: str | None = None) -> dict:
        """Manual path (Day 1 / fallback): ingest a PDF or page image you downloaded yourself."""
        stats = RunStats()
        key = f"{settings.source_alias}-{publication_date.isoformat()}"
        edition = EditionRef(publication_date, key, "", source_url or self.source.edition_url(publication_date), [])
        page = PageRef(page_number, source_url or edition.source_url, image_url or "")
        edition_id = f"ed_{key}"[:36]
        if not self.repo.get("editions", edition_id):
            self.repo.create("editions", edition_id, {
                "edition_key": key, "newspaper": settings.newspaper_name,
                "publication_date": publication_date.isoformat(), "source_url": edition.source_url,
                "status": "PROCESSING", "page_count": 0,
            })
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        self.process_page(edition, page, path, checksum, stats)
        self.repo.update("editions", edition_id, {
            "status": "PROCESSED", "processed_at": now_iso(), "classified_pages": [page_number],
            "jobs_found": stats.jobs_extracted, "checksum": checksum,
        })
        return asdict(stats)

    # ---- pages and ads

    def process_page(self, edition: EditionRef, page: PageRef, path: Path, checksum: str, stats: RunStats) -> None:
        lines = page_lines(path, checksum)
        width, height = _page_size(path)
        ads = extract.segment_ads(lines)
        jobs_ads = [a for a in ads if extract.is_recruitment(a)]
        log.info("Page %d: %d OCR lines, %d ads, %d recruitment ads", page.page_number, len(lines), len(ads), len(jobs_ads))
        stats.pages_processed += 1
        stats.ads_found += len(jobs_ads)
        for ad in jobs_ads:
            crop_id = None
            for draft in extract.extract_jobs(ad, edition.publication_date):
                crop_id = self.store_job(edition, page, ad, draft, width, height, stats, path, crop_id)

    def store_job(self, edition: EditionRef, page: PageRef, ad: Advertisement, draft: JobDraft,
                  width: int, height: int, stats: RunStats, image_path: Path | None = None,
                  crop_id: str | None = None) -> str | None:
        stats.jobs_extracted += 1
        should_publish = self.auto_publish
        content_hash = sha(extract.normalize_text(ad.text))
        appearance_id = "ap_" + sha(f"{edition.edition_key}|{content_hash}|{draft.role_index}", 32)
        if self.repo.get("job_appearances", appearance_id):
            stats.skipped_existing += 1     # same edition re-run: nothing new to record
            return crop_id

        if crop_id is None and image_path is not None and width:
            crop_id = "cr_" + sha(f"{edition.edition_key}|{content_hash}", 32)
            try:
                self.repo.save_crop(crop_id, _crop_jpeg(image_path, ad.bbox), public=should_publish)
            except Exception as exc:  # noqa: BLE001 - evidence image is helpful but not essential
                log.warning("Could not save crop for %s: %s", appearance_id, exc)
                crop_id = None

        pub = edition.publication_date.isoformat()
        exact = next((self.repo.get("jobs", a["job_id"]) for a in self.repo.find("job_appearances", "content_hash", content_hash)
                      if a.get("role_index", 0) == draft.role_index), None)
        since = (edition.publication_date - timedelta(days=90)).isoformat()
        candidates = [] if exact else self.repo.find_since("jobs", "last_seen_at", since)
        match = find_match(draft, ad.text, exact, candidates)

        job_fields = {
            "title": draft.title[:255], "employer": draft.employer, "description": draft.description[:10000],
            "location": draft.location, "qualification": draft.qualification, "experience": draft.experience,
            "salary_text": draft.salary_text, "contact_phones": draft.contact_phones,
            "contact_emails": draft.contact_emails, "application_instructions": draft.application_instructions,
            "deadline": draft.deadline,
        }

        if match.job is None:
            job_id = "job_" + sha(f"{edition.edition_key}|{content_hash}|{draft.role_index}", 32)
            low_confidence = draft.confidence < settings.review_confidence_threshold
            self.repo.create("jobs", job_id, {
                **job_fields,
                "newspaper": settings.newspaper_name, "first_seen_at": pub, "last_seen_at": pub,
                "appearance_count": 1,
                "review_status": "published" if should_publish else "needs_review",
                "confidence": draft.confidence,
                "uncertain_fields": draft.uncertain_fields + (["low_confidence"] if low_confidence else []),
                "has_pending_revision": False, "latest_appearance_id": appearance_id,
                "search_text": _search_text(draft)[:5000],
                **({"reviewed_by": "system_auto", "reviewed_at": now_iso()} if should_publish else {}),
            }, public=should_publish)
            stats.new_jobs += 1
            match_kind = "new"
        else:
            job = match.job
            job_id = job["$id"]
            update = {
                "last_seen_at": max(pub, job.get("last_seen_at") or pub),
                "first_seen_at": min(pub, job.get("first_seen_at") or pub),
                "appearance_count": int(job.get("appearance_count") or 1) + 1,
                "latest_appearance_id": appearance_id,
            }
            if should_publish:
                # In auto-publish mode, keep canonical job metadata strictly in sync with latest appearance
                update.update({
                    "title": draft.title[:255],
                    "employer": draft.employer,
                    "description": draft.description[:10000],
                    "location": draft.location,
                    "qualification": draft.qualification,
                    "experience": draft.experience,
                    "salary_text": draft.salary_text,
                    "contact_phones": draft.contact_phones,
                    "contact_emails": draft.contact_emails,
                    "application_instructions": draft.application_instructions,
                    "deadline": draft.deadline,
                    "search_text": _search_text(draft)[:5000],
                })
            else:
                update.update(filled_fields(job, draft))
                if match.needs_review:
                    update["has_pending_revision"] = True

            self.repo.update("jobs", job_id, update)
            stats.repeat_appearances += 1
            match_kind = match.kind

        self.repo.create("job_appearances", appearance_id, {
            "job_id": job_id, "edition_key": edition.edition_key, "publication_date": pub,
            "newspaper": settings.newspaper_name, "page_number": page.page_number,
            "ad_reference": ad.ad_reference, "section": ad.section, "extracted_text": ad.text[:10000],
            "content_hash": content_hash, "role_index": draft.role_index, "confidence": draft.confidence,
            "match_type": match_kind, "match_score": match.score, "source_url": page.viewer_url,
            "page_image_url": page.image_url or None, "bbox": [round(v) for v in ad.bbox],
            "page_width": width, "page_height": height, "crop_file_id": crop_id,
        }, public=bool(should_publish or (match.job and match.job.get("$public"))))

        if match.needs_review:
            if should_publish:
                self.repo.upsert("job_revisions", "rv_" + appearance_id[3:], {
                    "job_id": job_id, "appearance_id": appearance_id, "publication_date": pub,
                    "match_type": match_kind, "match_score": match.score, "status": "accepted",
                    "changed_fields": list(match.changes),
                    "old_values": json.dumps({k: v[0] for k, v in match.changes.items()}),
                    "new_values": json.dumps({k: v[1] for k, v in match.changes.items()}),
                    "created_at": now_iso(), "resolved_by": "system_auto", "resolved_at": now_iso(),
                })
            else:
                stats.revisions_flagged += 1
                self.repo.upsert("job_revisions", "rv_" + appearance_id[3:], {
                    "job_id": job_id, "appearance_id": appearance_id, "publication_date": pub,
                    "match_type": match_kind, "match_score": match.score, "status": "pending",
                    "changed_fields": list(match.changes),
                    "old_values": json.dumps({k: v[0] for k, v in match.changes.items()}),
                    "new_values": json.dumps({k: v[1] for k, v in match.changes.items()}),
                    "created_at": now_iso(),
                })
        return crop_id


def _crop_jpeg(path: Path, bbox, pad_x: int = 24, pad_y: int = 36, max_width: int = 900) -> bytes:
    with Image.open(path) as img:
        x0, y0, x1, y1 = bbox
        box = (max(0, int(x0) - pad_x), max(0, int(y0) - pad_y), min(img.width, int(x1) + pad_x), min(img.height, int(y1) + pad_y))
        crop = img.convert("RGB").crop(box)
    if crop.width > max_width:
        crop = crop.resize((max_width, round(crop.height * max_width / crop.width)))
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue()


def _search_text(d: JobDraft) -> str:
    parts = [d.title, d.employer, d.location, d.qualification, d.experience, d.description]
    return extract.normalize_text(" ".join(p for p in parts if p))


def _page_size(path: Path) -> tuple[int, int]:
    if path.suffix.lower() == ".pdf":
        return 0, 0
    with Image.open(path) as img:
        return img.size
