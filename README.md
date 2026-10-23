# Paper2Career

Turns newspaper recruitment classifieds into a searchable, date-aware job feed. Every listing links back to the newspaper page it was printed on. The feed shows when the ad first and last appeared and how its details changed between editions.

The first source is the **O Heraldo** e-paper (epaper.heraldgoa.in). Appwrite TablesDB is the system of record.

```
GitHub Actions (07:00 / 10:00 / 14:00 IST)
   └─ worker (Python)
        discover edition ─ download page JPGs ─ pick classifieds pages ─ OCR
        ─ split columns/sections/ads ─ drop property/vehicle/etc. ─ extract fields
        ─ match against history (hash, fuzzy text, shared phone) ─ write rows + run log
                                   │
                          Appwrite TablesDB  (paper2career_db)
                                   │
   React + Vite site: job feed · job detail with source crop + history · reviewer queue · ingestion status
```

## How the source is acquired

These details were checked against the live site in October 2026:

| What | Where |
| --- | --- |
| Edition page | `/epaper/oheraldo/DD-MM-YYYY` (404 until the edition is published) |
| Page list | `<a class="pagethumb" data-ed_date data-page data-id>` on the edition page |
| Page image | `/uploads/epaper/YYYY-MM/<hash>.jpg` (strip the `thumbnail-NNN-` prefix for full resolution) |
| robots.txt | allows everything except `/admin/` |

The site publishes no PDF for each page, so pages are acquired as JPG scans and OCR'd. Pages carry no section titles either, and the classifieds page moves (it was page 8 on 23 Oct 2026), so the worker finds it itself. It OCRs each page's 800 px preview (about 350 KB) looking for headings like *classified*, *SITUATIONS VACANT* and *WANTED*, then downloads only the matching page at full resolution (about 6 MB).

The worker identifies itself honestly (`Paper2Career/0.1` user agent) and waits 1.5 s between requests. It stops on any 401 or 403 instead of working around it. If the layout changes, the run is logged as `FAILED` with a `LayoutChanged` error, and no listings are invented.

If the site ever blocks automated access, use the manual import path with a PDF or JPG you downloaded yourself:

```
python -m paper2career import page4.pdf --date 2026-10-23 --page 4
```

## Data model (Appwrite TablesDB)

| Table | One row per | Notes |
| --- | --- | --- |
| `editions` | newspaper edition | status `PROCESSED`, `PARTIAL`, `NO_RECRUITMENT_FOUND`, … plus the classifieds pages and a checksum |
| `jobs` | canonical vacancy | `review_status` is `needs_review`, `published` or `rejected`. Has `first_seen_at`, `last_seen_at`, `appearance_count`, `has_pending_revision` |
| `job_appearances` | ad seen in one edition | page, section, OCR text, content hash, bbox on the page image, match type |
| `job_revisions` | detected change | old and new values for changed fields (deadline, salary, contact, …), pending until reviewed |
| `ingestion_runs` | worker run | `SUCCESS`, `NO_NEW_EDITION`, `PARTIAL` or `FAILED`, with counts and errors |

**Idempotency.** Row IDs are derived from `edition + content hash + role index`. Re-running an edition, or a retry after a partial failure, never creates duplicate rows.

**One ad, several jobs.** If an ad lists more than one role (for example "Driver and Cook"), each role becomes its own job, and all of them link to the same source ad.

**Permissions.** Writes come only from the worker's server API key and from members of the `reviewers` team. Rows have row-level security enabled. A job and its appearances become publicly readable (`read("any")`) only when a reviewer publishes them. The browser never holds an API key.

**Missing information stays unknown.** The extractor never fills in a salary or deadline that wasn't printed, and the site shows "Not stated in ad". When a deadline has passed, the site says so but does not claim the post is closed.

## Setup

### 1. Appwrite

1. Create a project named `Paper2Career` on [Appwrite Cloud](https://cloud.appwrite.io).
2. Create a **server API key** with these scopes: `databases.*`, `tables.*`, `columns.*`, `indexes.*`, `rows.*`, `buckets.*`, `files.*`, `teams.read`, `teams.write`.
3. Under **Auth**, enable Email/Password. Add a **Web platform** for your site's hostname (`localhost` for development, and your production domain).
4. Verify connection, create database, tables, storage bucket, and `reviewers` team:

   ```powershell
   cd worker
   py -3.12 -m venv .venv; .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env   # then fill in endpoint, project ID and API key (with AUTO_PUBLISH=true)

   # 1. Check your connection to Appwrite
   python -m paper2career check-appwrite

   # 2. Provision database, TablesDB tables, indexes, storage bucket, and team
   python -m paper2career setup

   # 3. (Optional) Seed existing curated local jobs and evidence crops to Appwrite Cloud
   python -m paper2career sync-to-appwrite
   ```

5. Create a user account for each reviewer under **Auth**, then add them to the **reviewers** team.

### 2. OCR engine

* **GitHub Actions / Linux:** the workflow runs `apt-get install tesseract-ocr`.
* **Windows:** nothing to install. The worker falls back to the built-in Windows 10/11 OCR (`scripts/winocr.ps1`, English language pack). Tesseract (set `TESSERACT_CMD`) or `pip install rapidocr onnxruntime` also work.

### 3. Daily automation (GitHub Actions)

Push this folder to a GitHub repository. Under **Settings → Secrets and variables → Actions**, add `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID` and `APPWRITE_API_KEY`.

The workflow in `.github/workflows/daily-ingestion.yml` runs the tests and then the ingestion at 07:00, 10:00 and 14:00 IST. Use **Run workflow** to process a specific date or specific pages manually. GitHub may delay scheduled runs by a few minutes.

### 4. Website

```powershell
cd frontend
npm install
copy .env.example .env.local   # set VITE_APPWRITE_ENDPOINT and VITE_APPWRITE_PROJECT_ID
npm run dev
```

If `VITE_APPWRITE_*` is not set, the site runs in **demo mode** and reads `public/demo-data.json`. Regenerate that file with `python -m paper2career --local export-demo` after a local run.

To deploy, build with `npm run build` and host `dist/`, for example on Appwrite Sites connected to this repository with root `frontend`, build command `npm run build` and output `dist`.

## Everyday commands

```powershell
cd worker
python -m paper2career run                                      # last 3 days, Appwrite
python -m paper2career run --date 2026-10-23 --page 4           # one page, skip detection
python -m paper2career --local run --date 2026-10-23            # JSON store (worker/data/) instead of Appwrite
python -m paper2career import scan.jpg --date 2026-10-23 --page 4
python -m pytest -q                                             # acceptance tests (no network/OCR needed)
```

## Acceptance tests

`worker/tests/test_pipeline.py` covers the SRS checklist using synthetic OCR output:

| Case | Test |
| --- | --- |
| Edition discovery | `test_edition_discovery_*` |
| Running the same edition twice | `test_rerunning_same_edition_creates_no_duplicates` |
| Category filtering (property and vehicles excluded) | `test_category_filtering_excludes_property_and_vehicles` |
| Repeated ad links to one record | `test_repeated_ad_links_to_existing_job`, `test_repeat_with_ocr_noise_still_matches` |
| Changed deadline flagged for review | `test_changed_deadline_creates_revision_for_review` |
| Source unavailable: run logged as failed, nothing published | `test_missing_source_logs_failure_and_publishes_nothing` |
| Missing fields stay unknown | `test_fields_extracted_and_missing_fields_stay_unknown` |
| Expired deadline wording | handled in `frontend/src/format.js` (`listingStatus`) |

Before you trust the extracted fields, OCR extraction should still be checked by hand against a real classifieds page.

## Known limitations

* Ad segmentation uses heuristics based on column positions and vertical gaps. Dense pages with boxed display ads will need tuning after the first real runs, and the reviewer queue is the safety net for this.
* All new jobs start as `needs_review`. Nothing is published automatically.
* Only O Heraldo is supported. Other papers need their own `source.py` adapter.
