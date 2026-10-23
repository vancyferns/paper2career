"""Paper2Career worker CLI.

  python -m paper2career setup                         create Appwrite database + tables (idempotent)
  python -m paper2career run [--date YYYY-MM-DD ...]   daily ingestion (default: last LOOKBACK_DAYS days)
  python -m paper2career import FILE --date D --page N ingest a PDF/JPG you downloaded yourself
  python -m paper2career publish-all                   auto-publish all pending jobs and appearances
  python -m paper2career export-demo                   dump the store to frontend/public/demo-data.json
Put --local (and optionally --local-db PATH) before the command to use a JSON store instead of Appwrite.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .repository import TABLES, open_repository

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paper2career")
    ap.add_argument("--local", action="store_true", help="use a local JSON store instead of Appwrite")
    ap.add_argument("--local-db", type=Path, default=ROOT / "data" / "local_db.json",
                    help="path of the local JSON store (with --local)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup")
    sub.add_parser("check-appwrite", help="verify connection and readiness of Appwrite Cloud")

    run = sub.add_parser("run")
    run.add_argument("--date", action="append", type=date.fromisoformat, help="edition date(s) to process")
    run.add_argument("--page", action="append", type=int, help="only these page numbers (skips page detection)")
    run.add_argument("--force", action="store_true", help="re-process editions already marked processed")
    run.add_argument("--trigger", default="manual")
    run.add_argument("--auto-publish", action="store_true", help="automatically publish newly extracted jobs")

    imp = sub.add_parser("import")
    imp.add_argument("file", type=Path)
    imp.add_argument("--date", required=True, type=date.fromisoformat)
    imp.add_argument("--page", required=True, type=int)
    imp.add_argument("--source-url")
    imp.add_argument("--auto-publish", action="store_true", help="automatically publish newly extracted jobs")

    pub = sub.add_parser("publish-all")
    pub.add_argument("--no-export-demo", dest="export_demo", action="store_false", default=True,
                     help="do not re-export frontend/public/demo-data.json")

    exp = sub.add_parser("export-demo")
    exp.add_argument("--out", type=Path, default=ROOT.parent / "frontend" / "public" / "demo-data.json")

    sync = sub.add_parser("sync-to-appwrite", help="push local database rows and crops to Appwrite Cloud")
    sync.add_argument("--local-db", type=Path, default=ROOT / "data" / "local_db.json")
    sync.add_argument("--crops-dir", type=Path, default=ROOT / "data" / "crops")

    pru = sub.add_parser("prune", help="delete ad crops and records older than N days to save storage")
    pru.add_argument("--days", type=int, default=7, help="retention window in days (default: 7)")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    local = args.local_db if args.local else None

    if args.cmd == "setup":
        from .setup_appwrite import setup
        setup()
        return 0

    if args.cmd == "check-appwrite":
        from .check_appwrite import check
        return check()

    repo = open_repository(local)

    if args.cmd == "run":
        from .pipeline import Ingestor
        auto_pub = True if args.auto_publish else None
        result = Ingestor(repo, auto_publish=auto_pub).run(days=args.date, trigger=args.trigger, pages=args.page, force=args.force)
        print(json.dumps(result, indent=2, default=str))
        return 1 if result["status"] == "FAILED" else 0

    if args.cmd == "import":
        from .pipeline import Ingestor
        auto_pub = True if args.auto_publish else None
        print(json.dumps(Ingestor(repo, auto_publish=auto_pub).import_file(args.file, args.date, args.page, args.source_url), indent=2))
        return 0

    if args.cmd == "publish-all":
        now = datetime.now(timezone.utc).isoformat()
        jobs_count = 0
        for job in repo.all("jobs"):
            if job.get("review_status") != "published" or not job.get("$public"):
                repo.update("jobs", job["$id"], {
                    "review_status": "published",
                    "reviewed_by": "system_auto",
                    "reviewed_at": now,
                }, public=True)
                jobs_count += 1
        apps_count = 0
        for app in repo.all("job_appearances"):
            if not app.get("$public"):
                repo.update("job_appearances", app["$id"], {}, public=True)
                apps_count += 1
        revs_count = 0
        for rev in repo.all("job_revisions"):
            if rev.get("status") == "pending":
                repo.update("job_revisions", rev["$id"], {
                    "status": "accepted",
                    "resolved_by": "system_auto",
                    "resolved_at": now,
                })
                revs_count += 1
        print(f"Auto-published {jobs_count} jobs, {apps_count} appearances, accepted {revs_count} revisions.")
        if args.export_demo:
            out = ROOT.parent / "frontend" / "public" / "demo-data.json"
            data = {t: repo.all(t) for t in TABLES}
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"Updated demo dataset at {out}")
        return 0

    if args.cmd == "export-demo":
        data = {t: repo.all(t) for t in TABLES}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {sum(len(v) for v in data.values())} rows to {args.out}")
        crops_src = getattr(repo, "path", ROOT / "data" / "x").parent / "crops"
        if crops_src.exists():
            import shutil
            crops_dst = args.out.parent / "crops"
            crops_dst.mkdir(exist_ok=True)
            wanted = {a.get("crop_file_id") for a in data["job_appearances"]}
            for f in crops_src.glob("*.jpg"):
                if f.stem in wanted:
                    shutil.copy2(f, crops_dst / f.name)
            print(f"Copied evidence crops to {crops_dst}")
        return 0

    if args.cmd == "sync-to-appwrite":
        from .config import settings
        if not settings.appwrite_configured:
            print("ERROR: Appwrite is not configured. Set APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID and APPWRITE_API_KEY in worker/.env", file=sys.stderr)
            return 1
        if not args.local_db.exists():
            print(f"ERROR: Local database file {args.local_db} does not exist.", file=sys.stderr)
            return 1

        local_data = json.loads(args.local_db.read_text(encoding="utf-8"))
        appwrite_repo = open_repository()

        # 1. Sync crops
        crops_dir = args.crops_dir
        if crops_dir.exists():
            crop_files = list(crops_dir.glob("*.jpg"))
            print(f"Syncing {len(crop_files)} ad crops to Appwrite Storage bucket 'ad_crops'...")
            for i, cf in enumerate(crop_files, 1):
                appwrite_repo.save_crop(cf.stem, cf.read_bytes(), public=True)
                if i % 50 == 0 or i == len(crop_files):
                    print(f"  Uploaded {i}/{len(crop_files)} crops")

        # 2. Sync editions, runs, revisions
        for table in ("editions", "ingestion_runs", "job_revisions"):
            rows = local_data.get(table, {})
            print(f"Syncing {len(rows)} rows to table '{table}'...")
            for row_id, r in rows.items():
                appwrite_repo.upsert(table, row_id, r, public=(table == "ingestion_runs"))

        # 3. Sync jobs
        jobs = local_data.get("jobs", {})
        print(f"Syncing {len(jobs)} jobs to table 'jobs'...")
        for row_id, j in jobs.items():
            is_pub = (j.get("review_status") == "published") or j.get("$public", False)
            appwrite_repo.upsert("jobs", row_id, j, public=is_pub)

        # 4. Sync appearances
        apps = local_data.get("job_appearances", {})
        print(f"Syncing {len(apps)} appearances to table 'job_appearances'...")
        for row_id, a in apps.items():
            parent_job = jobs.get(a.get("job_id", ""))
            is_pub = (parent_job and parent_job.get("review_status") == "published") or a.get("$public", False)
            appwrite_repo.upsert("job_appearances", row_id, a, public=is_pub)

        print("\nAll data successfully synced to Appwrite Cloud!")
        return 0

    if args.cmd == "prune":
        from .pipeline import Ingestor
        from .source import HeraldoSource
        pipe = Ingestor(repo)
        res = pipe.prune_older_than(days=args.days)
        print(f"Pruned {res['pruned_crops']} crops, {res['pruned_appearances']} appearances, {res['pruned_jobs']} jobs older than {res['cutoff']}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
